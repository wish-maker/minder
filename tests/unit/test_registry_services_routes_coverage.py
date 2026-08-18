"""Unit tests filling routes/services.py's remaining coverage gaps (73%).

test_registry_services_auth.py already locks in the auth gating (register/
unregister/proxy/health all require a JWT or service token; reads stay open)
and the persist-before-mutate Redis-failure contract for register/unregister.
This adds everything else: get_service's 404 + found branches,
unregister_service's 404 branch, check_service_health's healthy AND unhealthy
branches (previously entirely untested), proxy_to_service's query-string-
forwarding branch, and list_proxyable_services (previously entirely
untested).

Same module-loading pattern as the sibling suite (a fake `models` module
injected for the `from models import ServiceRegistration` import).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "routes"
    / "services.py"
)


class _FakeServiceRegistration(BaseModel):
    service_name: str
    service_type: str = "svc"
    host: str = "10.0.0.9"
    port: int = 8080
    health_check_url: str = ""
    metadata: dict = {}


@pytest.fixture(autouse=True)
def _fake_models_module():
    saved = sys.modules.get("models")
    fake_models = ModuleType("models")
    fake_models.ServiceRegistration = _FakeServiceRegistration
    sys.modules["models"] = fake_models
    try:
        yield
    finally:
        if saved is not None:
            sys.modules["models"] = saved
        else:
            sys.modules.pop("models", None)


def _load_route_module():
    spec = importlib.util.spec_from_file_location("reg_services_coverage", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


def _build(
    *,
    services_db=None,
    redis_client=None,
    proxy_router=None,
    auth=True,
):
    mod = _load_route_module()
    router = mod.build_services_router(
        services_db=services_db if services_db is not None else {},
        redis_client=redis_client or SimpleNamespace(),
        proxy_router=proxy_router,
        logger=_NoopLogger(),
    )
    app = FastAPI()
    app.include_router(router)
    if auth:
        app.dependency_overrides[mod.get_current_user_or_service] = lambda: {
            "sub": "tester"
        }
    return TestClient(app, raise_server_exceptions=False)


# --- get_service ---------------------------------------------------------------


def test_get_service_404_when_not_registered():
    client = _build(services_db={})
    r = client.get("/v1/services/unknown")
    assert r.status_code == 404


def test_get_service_returns_the_registered_service():
    svc = SimpleNamespace(service_name="weather", service_type="plugin")
    client = _build(services_db={"weather": svc})
    r = client.get("/v1/services/weather")
    assert r.status_code == 200


# --- unregister_service: 404 -----------------------------------------------


def test_unregister_service_404_when_not_registered():
    client = _build(services_db={})
    r = client.delete("/v1/services/unknown")
    assert r.status_code == 404


def test_unregister_service_success_removes_it():
    services_db = {"weather": SimpleNamespace(service_name="weather")}
    redis = SimpleNamespace(delete=lambda *a, **k: None)
    client = _build(services_db=services_db, redis_client=redis)

    r = client.delete("/v1/services/weather")

    assert r.status_code == 200
    assert "weather" not in services_db


# --- check_service_health -------------------------------------------------------


class _FakeRedis:
    def __init__(self):
        self.hset_calls = []

    def hset(self, key, mapping):
        self.hset_calls.append((key, mapping))

    def delete(self, *a, **k):
        pass

    def hget(self, *a, **k):
        return None


class _HealthyProxy:
    async def health_check_proxy(self, name):
        return {"status": "ok"}


class _UnhealthyProxy:
    async def health_check_proxy(self, name):
        raise HTTPException(status_code=503, detail="unreachable")


def test_check_service_health_records_healthy_status():
    redis = _FakeRedis()
    svc = SimpleNamespace(service_name="weather")
    client = _build(
        services_db={"weather": svc}, redis_client=redis, proxy_router=_HealthyProxy()
    )

    r = client.get("/v1/services/weather/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "healthy"
    assert body["health_data"] == {"status": "ok"}
    key, mapping = redis.hset_calls[0]
    assert key == "service:weather"
    assert mapping["health_status"] == "healthy"


def test_check_service_health_records_unhealthy_status_and_reraises():
    redis = _FakeRedis()
    svc = SimpleNamespace(service_name="weather")
    client = _build(
        services_db={"weather": svc},
        redis_client=redis,
        proxy_router=_UnhealthyProxy(),
    )

    r = client.get("/v1/services/weather/health")

    assert r.status_code == 503
    key, mapping = redis.hset_calls[0]
    assert key == "service:weather"
    assert mapping["health_status"] == "unhealthy"


# --- proxy_to_service: query-string forwarding -----------------------------------


class _CapturingProxy:
    def __init__(self):
        self.calls = []

    async def forward_request(self, service_name, path, request):
        self.calls.append((service_name, path))
        return {"forwarded": True}


def test_proxy_to_service_forwards_query_string():
    proxy = _CapturingProxy()
    svc = SimpleNamespace(service_name="weather")
    client = _build(services_db={"weather": svc}, proxy_router=proxy)

    r = client.get("/v1/proxy/weather/forecast", params={"city": "Ankara"})

    assert r.status_code == 200
    name, path = proxy.calls[0]
    assert name == "weather"
    assert path == "/forecast?city=Ankara"


def test_proxy_to_service_without_query_string():
    proxy = _CapturingProxy()
    client = _build(proxy_router=proxy)

    client.get("/v1/proxy/weather/forecast")

    name, path = proxy.calls[0]
    assert path == "/forecast"


# --- list_proxyable_services -----------------------------------------------------


def test_list_proxyable_services_includes_health_status_from_redis():
    class _RedisWithHealth:
        def hget(self, key, field):
            if key == "service:weather":
                return "healthy"
            return None

    svc = SimpleNamespace(
        service_name="weather",
        service_type="plugin",
        host="10.0.0.1",
        port=9000,
        metadata={"foo": "bar"},
    )
    client = _build(
        services_db={"weather": svc}, redis_client=_RedisWithHealth(), auth=False
    )

    r = client.get("/v1/proxy")

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    entry = body["services"][0]
    assert entry["service_name"] == "weather"
    assert entry["health_status"] == "healthy"
    assert entry["endpoint"] == "http://10.0.0.1:9000"


def test_list_proxyable_services_defaults_to_unknown_health(monkeypatch):
    class _RedisNoHealth:
        def hget(self, key, field):
            return None

    svc = SimpleNamespace(
        service_name="weather",
        service_type="plugin",
        host="10.0.0.1",
        port=9000,
        metadata={},
    )
    client = _build(
        services_db={"weather": svc}, redis_client=_RedisNoHealth(), auth=False
    )

    r = client.get("/v1/proxy")

    assert r.json()["services"][0]["health_status"] == "unknown"
