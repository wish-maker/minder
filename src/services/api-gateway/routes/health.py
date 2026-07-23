"""Observability routes: /health (phase-aware downstream checks) and /metrics."""

from datetime import datetime

from core.clients import http_client, redis_client
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from config import settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint with phase-aware downstream service status"""
    health_status = {
        "service": "api-gateway",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "phase": settings.MINDER_PHASE,
        "checks": {},
    }

    # Define critical services for each phase
    PHASE_1_SERVICES = ["redis", "plugin_registry"]
    PHASE_2_SERVICES = ["rag_pipeline", "model_management"]

    # All services to check (expanded to include AI services)
    ALL_SERVICES = {
        "redis": ("redis", lambda: redis_client.ping()),
        "plugin_registry": (
            settings.PLUGIN_REGISTRY_URL,
            lambda: http_client.get(
                f"{settings.PLUGIN_REGISTRY_URL}/health", timeout=5.0
            ),
        ),
        "rag_pipeline": (
            settings.RAG_PIPELINE_URL,
            lambda: http_client.get(f"{settings.RAG_PIPELINE_URL}/health", timeout=5.0),
        ),
        "model_management": (
            settings.MODEL_MANAGEMENT_URL,
            lambda: http_client.get(
                f"{settings.MODEL_MANAGEMENT_URL}/health", timeout=5.0
            ),
        ),
    }

    # Always check all services but mark Phase 2 as optional in Phase 1
    services_to_check = ALL_SERVICES

    # Determine which services are critical for current phase
    if settings.MINDER_PHASE == 1:
        critical_services = PHASE_1_SERVICES
    elif settings.MINDER_PHASE >= 2:
        critical_services = PHASE_1_SERVICES + PHASE_2_SERVICES
    else:
        critical_services = PHASE_1_SERVICES

    # Check only services relevant to current phase
    critical_unhealthy = False
    optional_unhealthy = False

    for service_name, (service_url, check_func) in services_to_check.items():
        try:
            if service_name == "redis":
                # Redis check
                check_func()
                health_status["checks"][service_name] = "healthy"
            else:
                # HTTP service check
                response = await check_func()
                if response.status_code == 200:
                    health_status["checks"][service_name] = "healthy"
                else:
                    health_status["checks"][
                        service_name
                    ] = f"unhealthy: HTTP {response.status_code}"
                    if service_name in critical_services:
                        critical_unhealthy = True
                    else:
                        optional_unhealthy = True
        except Exception as e:
            # Provide meaningful error messages
            error_type = type(e).__name__
            if error_type == "ReadTimeout":
                error_msg = "timeout after 5.0s"
            elif error_type == "ConnectError":
                error_msg = "connection refused"
            elif error_type == "ConnectTimeout":
                error_msg = "connection timeout"
            else:
                error_msg = str(e) if str(e) else error_type

            health_status["checks"][service_name] = f"unreachable: {error_msg}"
            if service_name in critical_services:
                critical_unhealthy = True
            else:
                optional_unhealthy = True

    # Determine overall status based on critical services
    if critical_unhealthy:
        health_status["status"] = "unhealthy"
        status_code = 503
    elif optional_unhealthy:
        # Only degraded if optional services are unhealthy
        health_status["status"] = "degraded"
        health_status[
            "message"
        ] = f"Phase {settings.MINDER_PHASE} active - Phase 2 services not started"
        status_code = 200  # Degraded is still functional, return 200
    else:
        health_status["status"] = "healthy"
        status_code = 200

    return JSONResponse(status_code=status_code, content=health_status)


@router.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
