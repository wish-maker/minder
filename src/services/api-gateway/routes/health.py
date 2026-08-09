"""Observability routes: /health (phase-aware downstream checks), /v1/status
(full-fleet health fan-out for the Status page), and /metrics."""

import asyncio
import sys
from datetime import datetime, timezone

from core.clients import http_client, redis_client
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config import settings

# Shared library on path (idempotent; also done in core/auth.py) so this route uses
# the shared dependency-check helper instead of hand-rolling the critical/optional →
# 503/degraded/200 loop that shared.health now owns (#141/#223).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.health import DependencyCheck, evaluate_dependencies  # noqa: E402

router = APIRouter()

# Critical dependencies per phase: Phase 1 needs redis + the plugin registry; Phase 2
# additionally treats the RAG/model services as critical. A non-critical dep being
# down is "degraded" (still 200), not "unhealthy" (503).
_PHASE_1 = {"redis", "plugin_registry"}
_PHASE_2 = {"rag_pipeline", "model_management"}


def _http_probe(base_url: str):
    """Build an async probe that fails unless the service's /health returns 200."""

    async def probe():
        response = await http_client.get(f"{base_url}/health", timeout=5.0)
        if response.status_code != 200:
            raise RuntimeError(f"HTTP {response.status_code}")

    return probe


@router.get("/health")
async def health_check():
    """Health check with phase-aware downstream dependency status."""
    phase = settings.MINDER_PHASE
    critical = _PHASE_1 | _PHASE_2 if phase >= 2 else _PHASE_1

    checks = [
        DependencyCheck(
            "redis", lambda: redis_client.ping(), critical="redis" in critical
        ),
        DependencyCheck(
            "plugin_registry",
            _http_probe(settings.PLUGIN_REGISTRY_URL),
            critical="plugin_registry" in critical,
        ),
        DependencyCheck(
            "rag_pipeline",
            _http_probe(settings.RAG_PIPELINE_URL),
            critical="rag_pipeline" in critical,
        ),
        DependencyCheck(
            "model_management",
            _http_probe(settings.MODEL_MANAGEMENT_URL),
            critical="model_management" in critical,
        ),
    ]

    status, status_code, check_results = await evaluate_dependencies(checks)

    body = {
        "service": "api-gateway",
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "phase": phase,
        "checks": check_results,
    }
    if status == "degraded":
        body["message"] = f"Phase {phase} active - Phase 2 services not started"

    return JSONResponse(status_code=status_code, content=body)


# Every service that exposes a shared.health-shaped /health, keyed by the name
# the Status page shows. tts-stt in particular may have no container at all in
# external-TTS-STT mode, which correctly reports as unreachable rather than
# crashing this endpoint.
_FLEET = [
    ("api-gateway", settings.API_GATEWAY_URL),
    ("plugin-registry", settings.PLUGIN_REGISTRY_URL),
    ("marketplace", settings.MARKETPLACE_URL),
    ("plugin-state-manager", settings.PLUGIN_STATE_MANAGER_URL),
    ("rag-pipeline", settings.RAG_PIPELINE_URL),
    ("model-management", settings.MODEL_MANAGEMENT_URL),
    ("tts-stt", settings.TTS_STT_URL),
    ("graph-rag", settings.GRAPH_RAG_URL),
]


async def _probe_fleet_service(name: str, base_url: str) -> dict:
    """Fetch one service's own /health body verbatim, reported as `reachable:
    false` (not a raised error) on any network failure or non-2xx response --
    a downed service is exactly the interesting case here, not an exception to
    propagate."""
    try:
        response = await http_client.get(f"{base_url}/health", timeout=5.0)
        body = response.json()
        return {
            "name": name,
            "reachable": True,
            "status": body.get("status", "unknown"),
            "version": body.get("version"),
            "environment": body.get("environment"),
            "checks": body.get("checks", {}),
        }
    except Exception as e:
        return {
            "name": name,
            "reachable": False,
            "status": "unreachable",
            "error": f"{type(e).__name__}: {e}"[:200],
        }


@router.get("/v1/status")
async def fleet_status():
    """Aggregate health across every core service for the client's Status page
    (#platform-status). No single-service /health today crosses the browser --
    each is internal-docker-network only -- so this is the one endpoint a
    browser can actually reach to see the whole fleet at once. `version` is
    each service's own hardcoded string, not derived from the deployed image
    tag -- a "reported version," not a deployment-tracking signal."""
    results = await asyncio.gather(
        *(_probe_fleet_service(name, url) for name, url in _FLEET)
    )
    return {"services": results}


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
