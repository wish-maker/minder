"""Unit tests for plugin-registry service-discovery auth (#SEC M1).

`POST /v1/services/register`, `DELETE /v1/services/{name}`, the dynamic
`/v1/proxy/{name}/{path}` forwarder, and `GET /v1/services/{name}/health` were
unauthenticated — the proxy/health ones forward to an arbitrary registered
host:port, i.e. an SSRF/lateral-movement primitive for any in-network caller. They
now require a valid user JWT OR the internal service token
(`get_current_user_or_service`). Pure reads (list/get) stay open per the platform's
GET-open policy (#47).

plugin-registry is a hyphenated service dir; `services.py` does `from models import
ServiceRegistration`. A fake `models` is injected/restored (the #142 collision), and
`SERVICE_SYNC_TOKEN` is monkeypatched so the service-token branch is exercised.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
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

_TOKEN = "test-service-token"


class _FakeServiceRegistration(BaseModel):
    service_name: str
    service_type: str = "svc"
    host: str = "10.0.0.9"
    port: int = 8080
    health_check_url: str = ""
    metadata: dict = {}


class _FakeProxy:
    async def forward_request(self, name, path, request):
        return {"proxied": name, "path": path}

    async def health_check_proxy(self, name):
        return {"ok": True}


@pytest.fixture
def client():
    import shared.auth.jwt_middleware as jm

    saved_models = sys.modules.get("models")
    saved_token = jm.SERVICE_SYNC_TOKEN
    fake_models = ModuleType("models")
    fake_models.ServiceRegistration = _FakeServiceRegistration
    sys.modules["models"] = fake_models
    jm.SERVICE_SYNC_TOKEN = _TOKEN
    try:
        spec = importlib.util.spec_from_file_location("reg_services_route", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        redis = SimpleNamespace(
            hset=lambda *a, **k: None,
            delete=lambda *a, **k: None,
            hget=lambda *a, **k: None,
        )
        app = FastAPI()
        app.include_router(
            mod.build_services_router(
                services_db={},
                redis_client=redis,
                proxy_router=_FakeProxy(),
                logger=SimpleNamespace(info=lambda *a, **k: None),
            )
        )
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        jm.SERVICE_SYNC_TOKEN = saved_token
        if saved_models is not None:
            sys.modules["models"] = saved_models
        else:
            sys.modules.pop("models", None)


def _svc_headers():
    return {"X-Service-Token": _TOKEN}


def test_proxy_requires_auth(client):
    # The SSRF sink: unauthenticated must be rejected.
    assert client.post("/v1/proxy/svc/some/path").status_code == 401


def test_proxy_allows_service_token(client):
    r = client.post("/v1/proxy/svc/some/path", headers=_svc_headers())
    assert r.status_code == 200
    assert r.json()["proxied"] == "svc"


def test_register_requires_auth(client):
    assert (
        client.post("/v1/services/register", json={"service_name": "x"}).status_code
        == 401
    )


def test_register_allows_service_token(client):
    r = client.post(
        "/v1/services/register",
        json={"service_name": "x"},
        headers=_svc_headers(),
    )
    assert r.status_code == 200


def test_unregister_and_health_require_auth(client):
    assert client.delete("/v1/services/x").status_code == 401
    assert client.get("/v1/services/x/health").status_code == 401


def test_reads_stay_open(client):
    # Pure reads are not gated (GET-open policy, #47).
    assert client.get("/v1/services").status_code == 200
    assert client.get("/v1/proxy").status_code == 200


# --- persist-before-mutate ordering -------------------------------------------
#
# Found in a background audit: register_service/unregister_service mutated
# services_db BEFORE the Redis call, with no try/except around Redis at all --
# load_services_from_redis() is what repopulates services_db on restart, so a
# Redis failure used to leave services_db (and a 200 response) claiming a
# registration/unregistration that never actually landed in Redis.


@pytest.fixture
def _redis_client_pair(monkeypatch):
    """Same models-module fake/restore dance as the `client` fixture above --
    needed here too since this helper does its own fresh module exec rather
    than reusing that fixture (it needs per-test hset/delete behavior)."""
    import shared.auth.jwt_middleware as jm

    saved_models = sys.modules.get("models")
    saved_token = jm.SERVICE_SYNC_TOKEN
    fake_models = ModuleType("models")
    fake_models.ServiceRegistration = _FakeServiceRegistration
    sys.modules["models"] = fake_models
    jm.SERVICE_SYNC_TOKEN = _TOKEN
    try:
        yield
    finally:
        jm.SERVICE_SYNC_TOKEN = saved_token
        if saved_models is not None:
            sys.modules["models"] = saved_models
        else:
            sys.modules.pop("models", None)


def _client_with_failing_redis(*, fail_hset=False, fail_delete=False):
    def _hset(*a, **k):
        if fail_hset:
            raise ConnectionError("redis down")

    def _delete(*a, **k):
        if fail_delete:
            raise ConnectionError("redis down")

    spec = importlib.util.spec_from_file_location("reg_services_route2", _ROUTE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    services_db = {}
    redis = SimpleNamespace(hset=_hset, delete=_delete, hget=lambda *a, **k: None)
    app = FastAPI()
    app.include_router(
        mod.build_services_router(
            services_db=services_db,
            redis_client=redis,
            proxy_router=_FakeProxy(),
            logger=SimpleNamespace(
                info=lambda *a, **k: None, error=lambda *a, **k: None
            ),
        )
    )
    return TestClient(app, raise_server_exceptions=False), services_db


def test_register_service_not_added_when_redis_fails(_redis_client_pair):
    client, services_db = _client_with_failing_redis(fail_hset=True)
    r = client.post(
        "/v1/services/register",
        json={"service_name": "x"},
        headers=_svc_headers(),
    )
    assert r.status_code == 503
    assert "x" not in services_db


def test_register_service_added_when_redis_succeeds(_redis_client_pair):
    client, services_db = _client_with_failing_redis(fail_hset=False)
    r = client.post(
        "/v1/services/register",
        json={"service_name": "x"},
        headers=_svc_headers(),
    )
    assert r.status_code == 200
    assert "x" in services_db


def test_unregister_service_kept_when_redis_fails(_redis_client_pair):
    client, services_db = _client_with_failing_redis(fail_delete=True)
    services_db["x"] = SimpleNamespace(service_name="x")
    r = client.delete("/v1/services/x", headers=_svc_headers())
    assert r.status_code == 503
    assert "x" in services_db  # must NOT have been removed while Redis delete failed
