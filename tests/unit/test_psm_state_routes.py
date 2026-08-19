"""Unit tests for plugin-state-manager's routes/state.py route layer.

core/state.py's domain logic (enable_plugin/disable_plugin/etc.) is exercised
elsewhere (test_psm_state_transitions.py); this covers the THIN routes/state.py
layer wrapping it, which had almost no direct coverage: DB-pool acquisition,
query-param validation (?state= filter), pagination, response shaping, the
domain-exception-to-HTTP-status mapping (_http_from_domain_error), and the
jsonb-serialization convention for config updates.

Same `_fresh_import` pattern as test_internal_write_endpoints_require_auth.py
(which already independently fresh-imports this same routes.state module in
the same pytest process) -- plugin-state-manager registers no module-level
Prometheus metrics, so repeated fresh imports across test files are safe.
"""

import importlib
import sys
from datetime import datetime, timezone
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


class _FakeConn:
    def __init__(self):
        self.execute = AsyncMock()


class _FakePool:
    def __init__(self, conn=None):
        self.conn = conn or _FakeConn()

    def acquire(self):
        return _FakeAcquireCtx(self.conn)


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
def state_mod(monkeypatch):
    mod = _fresh_import("plugin-state-manager", "routes.state")
    monkeypatch.setattr(mod, "get_db_pool", AsyncMock(return_value=_FakePool()))
    return mod


def _state_row(**overrides):
    now = datetime.now(timezone.utc)
    row = {
        "id": "id-1",
        "plugin_name": "weather",
        "state": "enabled",
        "license_tier": "community",
        "config": {},
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return row


# --- GET /state (list, filter, pagination) ----------------------------------


def test_list_all_plugin_states_returns_paginated_envelope(state_mod, monkeypatch):
    rows = [_state_row(id=f"id-{i}", plugin_name=f"plugin{i}") for i in range(3)]

    async def fake_list(conn, state_filter):
        assert state_filter is None
        return rows

    monkeypatch.setattr(state_mod, "list_plugin_states", fake_list)

    resp = _client(state_mod.router).get("/state")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 3
    assert body["total"] == 3
    assert len(body["plugins"]) == 3


def test_list_all_plugin_states_applies_state_filter(state_mod, monkeypatch):
    captured = {}

    async def fake_list(conn, state_filter):
        captured["filter"] = state_filter
        return [_state_row(state="disabled")]

    monkeypatch.setattr(state_mod, "list_plugin_states", fake_list)

    resp = _client(state_mod.router).get("/state", params={"state": "disabled"})

    assert resp.status_code == 200, resp.text
    assert captured["filter"] == state_mod.PluginState.DISABLED


def test_list_all_plugin_states_rejects_invalid_filter(state_mod):
    resp = _client(state_mod.router).get("/state", params={"state": "not-a-state"})

    assert resp.status_code == 422
    assert "Invalid state" in resp.json()["detail"]


def test_list_all_plugin_states_respects_limit_and_offset(state_mod, monkeypatch):
    rows = [_state_row(id=f"id-{i}", plugin_name=f"plugin{i}") for i in range(5)]

    async def fake_list(conn, state_filter):
        return rows

    monkeypatch.setattr(state_mod, "list_plugin_states", fake_list)

    resp = _client(state_mod.router).get("/state", params={"limit": 2, "offset": 1})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 2
    assert body["total"] == 5
    assert body["limit"] == 2
    assert body["offset"] == 1


# --- GET /state/{plugin_name} -------------------------------------------


def test_get_plugin_state_by_name_returns_state(state_mod, monkeypatch):
    async def fake_get(conn, plugin_name):
        assert plugin_name == "weather"
        return _state_row()

    monkeypatch.setattr(state_mod, "get_plugin_state", fake_get)

    resp = _client(state_mod.router).get("/state/weather")

    assert resp.status_code == 200, resp.text
    assert resp.json()["plugin_name"] == "weather"


def test_get_plugin_state_by_name_404_for_unknown_plugin(state_mod, monkeypatch):
    async def fake_get(conn, plugin_name):
        return None

    monkeypatch.setattr(state_mod, "get_plugin_state", fake_get)

    resp = _client(state_mod.router).get("/state/ghost")

    assert resp.status_code == 404


# --- POST /state/{plugin_name}/enable|disable (auth-gated) -----------------


def test_enable_plugin_endpoint_returns_updated_state(state_mod, monkeypatch):
    async def fake_enable(conn, plugin_name, reason):
        assert plugin_name == "weather"
        assert reason == "user request"
        return _state_row(state="enabled")

    monkeypatch.setattr(state_mod, "enable_plugin", fake_enable)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/weather/enable", json={"reason": "user request"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "enabled"


def test_enable_plugin_endpoint_maps_not_found_to_404_when_registry_also_lacks_it(
    state_mod, monkeypatch
):
    """A plugin unknown to BOTH plugin-state-manager and plugin-registry stays a
    plain 404 -- the #751 retry only kicks in when plugin-registry confirms the
    plugin genuinely exists. fake_enable deliberately SUCCEEDS when
    allow_create=True is passed (mirroring core.state.enable_plugin's real
    behavior, which doesn't itself know or care about registry existence) --
    so this test only passes if the route's own existence-check guard is what
    stops the retry from ever happening, not an accident of the mock."""
    calls = []

    async def fake_enable(conn, plugin_name, reason, allow_create=False):
        calls.append(allow_create)
        if not allow_create:
            raise state_mod.PluginNotFoundError(f"{plugin_name} not found")
        return _state_row(plugin_name=plugin_name, state="enabled")

    async def fake_exists(plugin_name):
        return False

    monkeypatch.setattr(state_mod, "enable_plugin", fake_enable)
    monkeypatch.setattr(state_mod, "plugin_exists_in_registry", fake_exists)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/ghost/enable", json={}
    )

    assert resp.status_code == 404
    assert calls == [False]  # retry with allow_create=True must never happen


def test_enable_plugin_endpoint_auto_creates_when_registry_confirms_existence(
    state_mod, monkeypatch
):
    """#751: a plugin with no state row yet, but that plugin-registry confirms is
    real, gets a retry with allow_create=True instead of a permanent 404."""
    calls = []

    async def fake_enable(conn, plugin_name, reason, allow_create=False):
        calls.append(allow_create)
        if not allow_create:
            raise state_mod.PluginNotFoundError(f"{plugin_name} not found")
        return _state_row(plugin_name=plugin_name, state="enabled")

    async def fake_exists(plugin_name):
        assert plugin_name == "weather-plus"
        return True

    monkeypatch.setattr(state_mod, "enable_plugin", fake_enable)
    monkeypatch.setattr(state_mod, "plugin_exists_in_registry", fake_exists)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/weather-plus/enable", json={}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["state"] == "enabled"
    assert calls == [False, True]  # first call bare, retry with allow_create=True


def test_enable_plugin_endpoint_503s_when_registry_unreachable(state_mod, monkeypatch):
    """Plugin-registry being unreachable during the existence check must be a
    retryable 503, never silently treated as either 'exists' or 'doesn't exist'."""

    async def fake_enable(conn, plugin_name, reason, allow_create=False):
        raise state_mod.PluginNotFoundError(f"{plugin_name} not found")

    async def fake_exists(plugin_name):
        raise ConnectionError("connection refused")

    monkeypatch.setattr(state_mod, "enable_plugin", fake_enable)
    monkeypatch.setattr(state_mod, "plugin_exists_in_registry", fake_exists)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/weather-plus/enable", json={}
    )

    assert resp.status_code == 503


def test_enable_plugin_endpoint_maps_state_transition_error_to_409(
    state_mod, monkeypatch
):
    async def fake_enable(conn, plugin_name, reason):
        raise state_mod.StateTransitionError("already enabled")

    monkeypatch.setattr(state_mod, "enable_plugin", fake_enable)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/weather/enable", json={}
    )

    assert resp.status_code == 409


def test_enable_plugin_endpoint_maps_generic_exception_to_500(state_mod, monkeypatch):
    async def fake_enable(conn, plugin_name, reason):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(state_mod, "enable_plugin", fake_enable)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/weather/enable", json={}
    )

    assert resp.status_code == 500
    assert "db exploded" not in resp.text


def test_disable_plugin_endpoint_passes_force_and_reason(state_mod, monkeypatch):
    captured = {}

    async def fake_disable(conn, plugin_name, force, reason):
        captured["force"] = force
        captured["reason"] = reason
        return _state_row(state="disabled")

    monkeypatch.setattr(state_mod, "disable_plugin", fake_disable)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/weather/disable", json={"force": True, "reason": "cleanup"}
    )

    assert resp.status_code == 200, resp.text
    assert captured == {"force": True, "reason": "cleanup"}


def test_disable_plugin_endpoint_maps_required_plugin_error_to_409(
    state_mod, monkeypatch
):
    async def fake_disable(conn, plugin_name, force, reason):
        raise state_mod.RequiredPluginError("core plugin cannot be disabled")

    monkeypatch.setattr(state_mod, "disable_plugin", fake_disable)

    resp = _client_with_service_auth(state_mod.router).post(
        "/state/core/disable", json={}
    )

    assert resp.status_code == 409


# --- PATCH /state/{plugin_name} (auth-gated) --------------------------------


def test_update_plugin_config_persists_serialized_json_and_returns_fresh_state(
    state_mod, monkeypatch
):
    calls = {"get": 0}

    async def fake_get(conn, plugin_name):
        calls["get"] += 1
        return _state_row(config={"threshold": 5} if calls["get"] > 1 else {})

    monkeypatch.setattr(state_mod, "get_plugin_state", fake_get)
    fake_pool = _FakePool()
    monkeypatch.setattr(state_mod, "get_db_pool", AsyncMock(return_value=fake_pool))

    resp = _client_with_service_auth(state_mod.router).patch(
        "/state/weather", json={"config": {"threshold": 5}}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["config"] == {"threshold": 5}
    # config must be JSON-serialized before binding (asyncpg has no jsonb codec).
    args, _ = fake_pool.conn.execute.call_args
    assert args[1] == '{"threshold": 5}'
    assert args[2] == "weather"


def test_update_plugin_config_404_for_unknown_plugin(state_mod, monkeypatch):
    async def fake_get(conn, plugin_name):
        return None

    monkeypatch.setattr(state_mod, "get_plugin_state", fake_get)

    resp = _client_with_service_auth(state_mod.router).patch(
        "/state/ghost", json={"config": {}}
    )

    assert resp.status_code == 404


# --- dependency endpoints ---------------------------------------------------


def test_get_plugin_dependencies_reports_dependents_and_count(state_mod, monkeypatch):
    async def fake_dependents(conn, plugin_name):
        return ["a", "b"]

    monkeypatch.setattr(state_mod, "get_dependent_plugins", fake_dependents)

    resp = _client(state_mod.router).get("/weather/dependencies")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "plugin_name": "weather",
        "dependents": ["a", "b"],
        "count": 2,
    }


def test_resolve_plugin_dependencies_returns_enable_order(state_mod, monkeypatch):
    async def fake_resolve(conn, plugin_name):
        return ["dep1", "dep2", "weather"]

    monkeypatch.setattr(state_mod, "resolve_dependencies", fake_resolve)

    resp = _client(state_mod.router).post("/weather/dependencies/resolve")

    assert resp.status_code == 200, resp.text
    assert resp.json()["enable_order"] == ["dep1", "dep2", "weather"]
    assert resp.json()["count"] == 3


def test_resolve_plugin_dependencies_maps_not_found_to_404(state_mod, monkeypatch):
    async def fake_resolve(conn, plugin_name):
        raise state_mod.PluginNotFoundError("ghost not found")

    monkeypatch.setattr(state_mod, "resolve_dependencies", fake_resolve)

    resp = _client(state_mod.router).post("/ghost/dependencies/resolve")

    assert resp.status_code == 404
