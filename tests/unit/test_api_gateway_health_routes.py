"""Unit tests for api-gateway's routes/health.py -- /health (phase-aware
downstream checks) and /v1/status (fleet-wide fan-out backing the client's
Status page / HealthStrip) had zero coverage (49% per `coverage run`).

api-gateway is a hyphenated service dir; health.py imports `from core.clients
import http_client, redis_client` and `from config import settings` at module
top -- fakes for both injected and restored, matching
test_api_gateway_middleware.py's precedent.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

_MOD_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "health.py"
)


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json_body = json_body if json_body is not None else {}

    def json(self):
        return self._json_body


class _FakeHttpClient:
    """Routes by a substring of the base_url. A missing entry raises (simulating
    an unreachable service); an entry may be a _FakeResponse or an exception
    instance/class to raise."""

    def __init__(self, responses):
        self._responses = responses

    async def get(self, url, timeout=None):
        for key, value in self._responses.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise ConnectionError(f"no fake route for {url}")


class _FakeRedis:
    def __init__(self, raises=None):
        self._raises = raises

    def ping(self):
        if self._raises:
            raise self._raises
        return True


def _load_health(*, phase=1, http_responses=None, redis=None):
    names = ("config", "core", "core.clients")
    saved = {n: sys.modules.get(n) for n in names}
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        MINDER_PHASE=phase,
        PLUGIN_REGISTRY_URL="http://plugin-registry:8001",
        RAG_PIPELINE_URL="http://rag-pipeline:8004",
        MODEL_MANAGEMENT_URL="http://model-management:8005",
        MARKETPLACE_URL="http://marketplace:8002",
        PLUGIN_STATE_MANAGER_URL="http://plugin-state-manager:8003",
        TTS_STT_URL="http://tts-stt:8006",
        GRAPH_RAG_URL="http://graph-rag:8008",
        API_GATEWAY_URL="http://api-gateway:8000",
        APP_VERSION="1.0.0",
        ENVIRONMENT="test",
    )
    sys.modules["config"] = cfg
    sys.modules["core"] = ModuleType("core")
    fake_clients = ModuleType("core.clients")
    fake_clients.http_client = _FakeHttpClient(http_responses or {})
    fake_clients.redis_client = redis if redis is not None else _FakeRedis()
    sys.modules["core.clients"] = fake_clients
    try:
        spec = importlib.util.spec_from_file_location("gateway_health_uut", _MOD_PATH)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)


def _client(mod):
    app = FastAPI()
    app.include_router(mod.router)
    return TestClient(app)


_HEALTHY = {
    "plugin-registry": _FakeResponse(200),
    "rag-pipeline": _FakeResponse(200),
    "model-management": _FakeResponse(200),
}


class TestHealthCheck:
    def test_all_healthy_is_200_with_no_message(self):
        mod = _load_health(phase=1, http_responses=_HEALTHY)
        r = _client(mod).get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "healthy"
        assert "message" not in body

    def test_redis_down_is_always_critical_503(self):
        mod = _load_health(
            phase=1,
            http_responses=_HEALTHY,
            redis=_FakeRedis(raises=ConnectionError("redis down")),
        )
        r = _client(mod).get("/health")
        assert r.status_code == 503
        assert r.json()["status"] == "unhealthy"

    def test_phase_1_treats_rag_pipeline_as_non_critical_degraded(self):
        responses = dict(_HEALTHY)
        responses["rag-pipeline"] = ConnectionError("down")
        mod = _load_health(phase=1, http_responses=responses)
        r = _client(mod).get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "degraded"
        assert "message" in body
        assert "Phase 1" in body["message"]

    def test_phase_2_treats_rag_pipeline_as_critical_503(self):
        responses = dict(_HEALTHY)
        responses["rag-pipeline"] = ConnectionError("down")
        mod = _load_health(phase=2, http_responses=responses)
        r = _client(mod).get("/health")
        assert r.status_code == 503
        assert r.json()["status"] == "unhealthy"

    def test_plugin_registry_down_is_critical_in_every_phase(self):
        responses = dict(_HEALTHY)
        responses["plugin-registry"] = ConnectionError("down")
        mod = _load_health(phase=1, http_responses=responses)
        r = _client(mod).get("/health")
        assert r.status_code == 503

    def test_a_non_200_probe_response_counts_as_down(self):
        responses = dict(_HEALTHY)
        responses["plugin-registry"] = _FakeResponse(500)
        mod = _load_health(phase=1, http_responses=responses)
        r = _client(mod).get("/health")
        assert r.status_code == 503


class TestFleetStatus:
    def test_reports_every_service_reachable_with_its_body_fields(self):
        responses = {
            name: _FakeResponse(
                200,
                {"status": "healthy", "version": "1.0.0", "environment": "test"},
            )
            for name in (
                "api-gateway",
                "plugin-registry",
                "marketplace",
                "plugin-state-manager",
                "rag-pipeline",
                "model-management",
                "tts-stt",
                "graph-rag",
            )
        }
        mod = _load_health(http_responses=responses)
        r = _client(mod).get("/v1/status")
        assert r.status_code == 200
        services = r.json()["services"]
        assert len(services) == 8
        assert all(s["reachable"] is True for s in services)
        assert all(s["status"] == "healthy" for s in services)

    def test_reports_an_unreachable_service_without_crashing_the_whole_call(self):
        responses = {
            "api-gateway": _FakeResponse(200, {"status": "healthy"}),
            "plugin-registry": _FakeResponse(200, {"status": "healthy"}),
            "marketplace": _FakeResponse(200, {"status": "healthy"}),
            "plugin-state-manager": _FakeResponse(200, {"status": "healthy"}),
            "model-management": _FakeResponse(200, {"status": "healthy"}),
            "tts-stt": _FakeResponse(200, {"status": "healthy"}),
            "graph-rag": _FakeResponse(200, {"status": "healthy"}),
            # rag-pipeline deliberately absent -> _FakeHttpClient raises for it.
        }
        mod = _load_health(http_responses=responses)
        r = _client(mod).get("/v1/status")
        assert r.status_code == 200
        services = {s["name"]: s for s in r.json()["services"]}
        down = services["rag-pipeline"]
        assert down["reachable"] is False
        assert down["status"] == "unreachable"
        assert "error" in down

    def test_truncates_a_very_long_error_message(self):
        responses = {
            "api-gateway": _FakeResponse(200, {"status": "healthy"}),
            "plugin-registry": _FakeResponse(200, {"status": "healthy"}),
            "marketplace": _FakeResponse(200, {"status": "healthy"}),
            "plugin-state-manager": _FakeResponse(200, {"status": "healthy"}),
            "rag-pipeline": _FakeResponse(200, {"status": "healthy"}),
            "model-management": _FakeResponse(200, {"status": "healthy"}),
            "tts-stt": _FakeResponse(200, {"status": "healthy"}),
            "graph-rag": RuntimeError("x" * 500),
        }
        mod = _load_health(http_responses=responses)
        r = _client(mod).get("/v1/status")
        services = {s["name"]: s for s in r.json()["services"]}
        assert len(services["graph-rag"]["error"]) <= 200
