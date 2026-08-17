"""Unit tests for plugin-state-manager's routes/tools.py route layer.

core/execution.py's discover_tools/discover_plugin_tools/execute_tool internals
are already covered by test_psm_tool_discovery.py, and core/execution.py's
parameter coercion/validation by test_psm_tool_validation.py -- neither
exercises the routes/tools.py HTTP layer itself: pagination, the tier query
filter, 404-on-unknown-tool, and backend_http_error's exception mapping on
every route, including validate_tool_license's LAZY (inside-the-function-body)
imports of core.database/core.license.

Same `_fresh_import` pattern as test_internal_write_endpoints_require_auth.py
-- plugin-state-manager registers no module-level Prometheus metrics, so
repeated fresh imports across test files are safe.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
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
    # tools.router has a bare "" GET route (list_all_tools) -- mounting at "/"
    # with no prefix makes FastAPI reject the combined empty path, unrelated
    # to what's under test here (same precedent as
    # test_internal_write_endpoints_require_auth.py). Every request path
    # below is written relative to this "/tools" prefix.
    app = FastAPI()
    app.include_router(router, prefix="/tools")
    return TestClient(app, raise_server_exceptions=False)


def _client_with_service_auth(router) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/tools")
    app.dependency_overrides[get_current_user_or_service] = lambda: {
        "sub": "internal-service",
        "role": "service",
    }
    return TestClient(app, raise_server_exceptions=False)


def _tool_schema(name="get_weather", **overrides):
    """A real models.tool_execution.ToolSchema instance -- production code
    (get_tool_details/discover_tools) accesses `.name` attribute-style, so a
    plain dict stand-in fails with AttributeError rather than exercising the
    intended branch."""
    models_mod = importlib.import_module("models.tool_execution")
    fields = {
        "name": name,
        "description": "Get current weather",
        "type": "data",
        "parameters": {},
        "response_format": {},
        "endpoint": "/weather",
        "method": "GET",
        "required_tier": "community",
    }
    fields.update(overrides)
    return models_mod.ToolSchema(**fields)


class _FakeDiscoveryResult:
    def __init__(self, tools):
        self.tools = tools


@pytest.fixture
def tools_mod(monkeypatch):
    mod = _fresh_import("plugin-state-manager", "routes.tools")
    # validate_tool_license imports these lazily inside the function body --
    # load them into sys.modules now (via the same sys.path _fresh_import just
    # set up) so they can be monkeypatched the same way as everything else.
    db_mod = importlib.import_module("core.database")
    license_mod = importlib.import_module("core.license")
    monkeypatch.setattr(db_mod, "get_db_pool", AsyncMock(return_value=_FakePool()))
    mod._db_mod = db_mod
    mod._license_mod = license_mod
    return mod


# --- GET "" (list_all_tools) -------------------------------------------


def test_list_all_tools_returns_paginated_envelope(tools_mod, monkeypatch):
    tools = [_tool_schema(name=f"tool{i}") for i in range(3)]

    async def fake_discover(active_only, tier_filter):
        assert active_only is True
        assert tier_filter is None
        return _FakeDiscoveryResult(tools)

    monkeypatch.setattr(tools_mod, "discover_tools", fake_discover)

    resp = _client(tools_mod.router).get("/tools")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 3
    assert body["total"] == 3


def test_list_all_tools_forwards_tier_filter_and_pagination(tools_mod, monkeypatch):
    captured = {}
    tools = [_tool_schema(name=f"tool{i}") for i in range(5)]

    async def fake_discover(active_only, tier_filter):
        captured["active_only"] = active_only
        captured["tier_filter"] = tier_filter
        return _FakeDiscoveryResult(tools)

    monkeypatch.setattr(tools_mod, "discover_tools", fake_discover)

    resp = _client(tools_mod.router).get(
        "/tools",
        params={"active_only": "false", "tier": "pro", "limit": 2, "offset": 1},
    )

    assert resp.status_code == 200, resp.text
    assert captured == {"active_only": False, "tier_filter": "pro"}
    body = resp.json()
    assert body["count"] == 2
    assert body["total"] == 5


def test_list_all_tools_maps_exception_via_backend_http_error(tools_mod, monkeypatch):
    async def boom(active_only, tier_filter):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tools_mod, "discover_tools", boom)

    resp = _client(tools_mod.router).get("/tools")

    assert resp.status_code == 500
    assert "db exploded" not in resp.text


# --- GET /{tool_name} (get_tool_details) ------------------------------------


def test_get_tool_details_returns_the_matching_tool(tools_mod, monkeypatch):
    tools = [_tool_schema(name="weather"), _tool_schema(name="crypto")]

    async def fake_discover():
        return _FakeDiscoveryResult(tools)

    monkeypatch.setattr(tools_mod, "discover_tools", fake_discover)

    resp = _client(tools_mod.router).get("/tools/crypto")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["count"] == 1
    assert body["tools"][0]["name"] == "crypto"


def test_get_tool_details_404_for_unknown_tool(tools_mod, monkeypatch):
    async def fake_discover():
        return _FakeDiscoveryResult([_tool_schema(name="weather")])

    monkeypatch.setattr(tools_mod, "discover_tools", fake_discover)

    resp = _client(tools_mod.router).get("/tools/ghost")

    assert resp.status_code == 404


def test_get_tool_details_maps_exception_via_backend_http_error(tools_mod, monkeypatch):
    async def boom():
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tools_mod, "discover_tools", boom)

    resp = _client(tools_mod.router).get("/tools/weather")

    assert resp.status_code == 500
    assert "db exploded" not in resp.text


# --- POST /{tool_name}/execute (auth-gated) ---------------------------------


def test_execute_tool_endpoint_uses_the_verified_identity(tools_mod, monkeypatch):
    captured = {}

    async def fake_execute(tool_name, parameters, user_id):
        captured["tool_name"] = tool_name
        captured["parameters"] = parameters
        captured["user_id"] = user_id
        return {
            "tool_name": tool_name,
            "plugin_name": "weather-plugin",
            "result": {"temp": 20},
            "execution_time": 0.05,
            "tier_required": "community",
        }

    monkeypatch.setattr(tools_mod, "execute_tool", fake_execute)

    # A "user_id" smuggled inside the free-form `parameters` dict must be
    # ignored -- the license/tier check must run against the VERIFIED caller
    # identity (the JWT's `sub`), never a client-suppliable field (per this
    # route's own docstring).
    resp = _client_with_service_auth(tools_mod.router).post(
        "/tools/weather/execute",
        json={"parameters": {"city": "Ankara", "user_id": "someone-else"}},
    )

    assert resp.status_code == 200, resp.text
    # The verified identity wins regardless of what's smuggled in parameters
    # -- parameters itself is forwarded verbatim (it's a free-form dict, not
    # filtered), but user_id must come from current_user["sub"], not there.
    assert captured["user_id"] == "internal-service"
    assert captured["parameters"] == {"city": "Ankara", "user_id": "someone-else"}


def test_execute_tool_endpoint_propagates_httpexception_unwrapped(
    tools_mod, monkeypatch
):
    async def fake_execute(tool_name, parameters, user_id):
        raise HTTPException(status_code=403, detail="tier too low")

    monkeypatch.setattr(tools_mod, "execute_tool", fake_execute)

    resp = _client_with_service_auth(tools_mod.router).post(
        "/tools/weather/execute", json={"parameters": {}}
    )

    assert resp.status_code == 403
    assert resp.json()["detail"] == "tier too low"


def test_execute_tool_endpoint_maps_generic_exception_via_backend_http_error(
    tools_mod, monkeypatch
):
    async def boom(tool_name, parameters, user_id):
        raise RuntimeError("plugin crashed")

    monkeypatch.setattr(tools_mod, "execute_tool", boom)

    resp = _client_with_service_auth(tools_mod.router).post(
        "/tools/weather/execute", json={"parameters": {}}
    )

    assert resp.status_code == 500
    assert "plugin crashed" not in resp.text


# --- GET /plugins/{plugin_id}/tools -----------------------------------------


def test_list_plugin_tools_validates_plugin_id_before_querying(tools_mod, monkeypatch):
    called = []
    monkeypatch.setattr(
        tools_mod,
        "discover_plugin_tools",
        AsyncMock(side_effect=lambda pid: called.append(pid)),
    )

    resp = _client(tools_mod.router).get("/tools/plugins/not-a-uuid/tools")

    assert resp.status_code == 404
    assert called == []  # rejected before ever calling discover_plugin_tools


def test_list_plugin_tools_returns_discovery_result(tools_mod, monkeypatch):
    plugin_id = "11111111-1111-1111-1111-111111111111"

    async def fake_discover(pid):
        assert pid == plugin_id
        return tools_mod.ToolDiscoveryResponse(tools=[_tool_schema()], count=1)

    monkeypatch.setattr(tools_mod, "discover_plugin_tools", fake_discover)

    resp = _client(tools_mod.router).get(f"/tools/plugins/{plugin_id}/tools")

    assert resp.status_code == 200, resp.text
    assert resp.json()["count"] == 1


def test_list_plugin_tools_passes_through_404_from_discovery(tools_mod, monkeypatch):
    plugin_id = "11111111-1111-1111-1111-111111111111"

    async def fake_discover(pid):
        raise HTTPException(status_code=404, detail="plugin not found")

    monkeypatch.setattr(tools_mod, "discover_plugin_tools", fake_discover)

    resp = _client(tools_mod.router).get(f"/tools/plugins/{plugin_id}/tools")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "plugin not found"


def test_list_plugin_tools_maps_generic_exception_via_backend_http_error(
    tools_mod, monkeypatch
):
    plugin_id = "11111111-1111-1111-1111-111111111111"

    async def boom(pid):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tools_mod, "discover_plugin_tools", boom)

    resp = _client(tools_mod.router).get(f"/tools/plugins/{plugin_id}/tools")

    assert resp.status_code == 500
    assert "db exploded" not in resp.text


# --- POST /validate ----------------------------------------------------------


def test_validate_tool_license_returns_validation_result(tools_mod, monkeypatch):
    async def fake_validate(conn, user_id, tool_name):
        assert user_id == "user-1"
        assert tool_name == "premium_tool"
        return {
            "allowed": False,
            "tier_required": "pro",
            "user_tier": "community",
            "reason": "requires pro tier or higher",
        }

    monkeypatch.setattr(tools_mod._license_mod, "validate_tool_access", fake_validate)

    resp = _client(tools_mod.router).post(
        "/tools/validate", json={"user_id": "user-1", "tool_name": "premium_tool"}
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["allowed"] is False
    assert body["tier_required"] == "pro"


def test_validate_tool_license_maps_exception_via_backend_http_error(
    tools_mod, monkeypatch
):
    async def boom(conn, user_id, tool_name):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(tools_mod._license_mod, "validate_tool_access", boom)

    resp = _client(tools_mod.router).post(
        "/tools/validate", json={"user_id": "user-1", "tool_name": "premium_tool"}
    )

    assert resp.status_code == 500
    assert "db exploded" not in resp.text
