"""Unit tests for plugin-state-manager's routes/licensing.py route layer.

core/license.py's underlying logic is already thoroughly unit-tested
(test_psm_license.py) -- this covers the THIN route handlers themselves,
which had almost no direct coverage: DB-pool acquisition, shaping the
result into the response models, the 404-on-missing-plugin mapping, and
backend_http_error's exception-to-status-code mapping.

Same `_fresh_import` pattern as test_internal_write_endpoints_require_auth.py
(which already independently fresh-imports this same routes.licensing
module in the same pytest process) -- plugin-state-manager registers no
module-level Prometheus metrics, so repeated fresh imports across test
files are safe (unlike rag-pipeline's core.state).
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.auth.jwt_middleware import get_current_user_or_service

_SERVICES = Path(__file__).resolve().parents[2] / "src" / "services"


def _fresh_import(service_dir: str, module_path: str):
    sys.path.insert(0, str(_SERVICES / service_dir))
    for stale in list(sys.modules):
        if stale.split(".")[0] in ("core", "config", "models", "routes", "domain"):
            del sys.modules[stale]
    return importlib.import_module(module_path)


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def acquire(self):
        return _FakeAcquireCtx(object())


def _client(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _client_with_service_auth(router) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_or_service] = lambda: {
        "sub": "internal-service",
        "role": "service",
    }
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def licensing(monkeypatch):
    mod = _fresh_import("plugin-state-manager", "routes.licensing")
    monkeypatch.setattr(mod, "get_db_pool", AsyncMock(return_value=_FakePool()))
    return mod


# --- GET .../license/tier -----------------------------------------------


def test_get_plugin_tier_returns_required_tier(licensing, monkeypatch):
    async def fake_get_tier(conn, plugin_name):
        assert plugin_name == "weather"
        return licensing.LicenseTier.PRO

    monkeypatch.setattr(licensing, "get_plugin_license_tier", fake_get_tier)

    resp = _client(licensing.router).get("/plugins/weather/license/tier")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"plugin_name": "weather", "required_tier": "pro"}


def test_get_plugin_tier_maps_exception_via_backend_http_error(licensing, monkeypatch):
    async def boom(conn, plugin_name):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(licensing, "get_plugin_license_tier", boom)

    resp = _client(licensing.router).get("/plugins/weather/license/tier")

    assert resp.status_code == 500
    assert "db exploded" not in resp.text  # sanitized, not leaked


# --- POST .../license/validate --------------------------------------------


def test_validate_plugin_license_returns_validation_result(licensing, monkeypatch):
    async def fake_check(conn, plugin_name, license_key):
        assert plugin_name == "weather"
        assert license_key == "key-123"
        return {"valid": True, "tier": "pro", "message": "ok"}

    monkeypatch.setattr(licensing, "check_plugin_license", fake_check)

    resp = _client(licensing.router).post(
        "/plugins/weather/license/validate", json={"license_key": "key-123"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"valid": True, "tier": "pro", "message": "ok"}


def test_validate_plugin_license_defaults_license_key_to_none(licensing, monkeypatch):
    captured = {}

    async def fake_check(conn, plugin_name, license_key):
        captured["license_key"] = license_key
        return {"valid": True, "tier": "community", "message": "ok"}

    monkeypatch.setattr(licensing, "check_plugin_license", fake_check)

    resp = _client(licensing.router).post("/plugins/weather/license/validate", json={})

    assert resp.status_code == 200, resp.text
    assert captured["license_key"] is None


def test_validate_plugin_license_maps_exception_via_backend_http_error(
    licensing, monkeypatch
):
    async def boom(conn, plugin_name, license_key):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(licensing, "check_plugin_license", boom)

    resp = _client(licensing.router).post("/plugins/weather/license/validate", json={})

    assert resp.status_code == 500
    assert "db exploded" not in resp.text


# --- PATCH .../license (auth-gated) ---------------------------------------


def test_update_plugin_license_returns_updated_fields(licensing, monkeypatch):
    async def fake_update(conn, plugin_name, license_tier, license_key):
        return {
            "license_tier": license_tier.value,
            "license_key": license_key,
            "updated_at": "2026-08-17T00:00:00+00:00",
        }

    monkeypatch.setattr(licensing, "update_plugin_license", fake_update)

    resp = _client_with_service_auth(licensing.router).patch(
        "/plugins/weather/license",
        json={"license_tier": "pro", "license_key": "key-123"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plugin_name"] == "weather"
    assert body["license_tier"] == "pro"
    assert body["license_key"] == "key-123"


def test_update_plugin_license_404_for_unknown_plugin(licensing, monkeypatch):
    async def fake_update(conn, plugin_name, license_tier, license_key):
        return None

    monkeypatch.setattr(licensing, "update_plugin_license", fake_update)

    resp = _client_with_service_auth(licensing.router).patch(
        "/plugins/ghost/license", json={"license_tier": "community"}
    )

    assert resp.status_code == 404


def test_update_plugin_license_maps_generic_exception_not_as_404(
    licensing, monkeypatch
):
    async def boom(conn, plugin_name, license_tier, license_key):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(licensing, "update_plugin_license", boom)

    resp = _client_with_service_auth(licensing.router).patch(
        "/plugins/weather/license", json={"license_tier": "pro"}
    )

    assert resp.status_code == 500
    assert "db exploded" not in resp.text
