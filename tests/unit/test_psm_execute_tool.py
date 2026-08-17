"""Unit tests for plugin-state-manager's core/execution.py::execute_tool.

execute_tool was ENTIRELY untested (0% of its ~100 lines) -- its own docstring-
adjacent comment in _build_execution_url explains why: it has real lazy
imports of core.database/core.license/core.state inside its body, which the
service's simpler isolated-import test harness deliberately excludes. This
uses the SAME lazy-import-injection pattern already established for
routes/tools.py's validate_tool_license (test_psm_tool_routes.py): _fresh_import
leaves sys.path/sys.modules mutated (no cleanup -- plugin-state-manager
registers no module-level Prometheus metrics, so this is safe across files),
then core.database/core.license/core.state are imported via the SAME sys.path
entry so execute_tool's own lazy imports resolve to these exact module
objects and can be monkeypatched.

discover_tools' tier_filter branch (previously untested) is covered here too,
in the same file since it needs the identical httpx.AsyncClient fake.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

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


@pytest.fixture
def execution_mod(monkeypatch):
    mod = _fresh_import("plugin-state-manager", "core.execution")
    db_mod = importlib.import_module("core.database")
    license_mod = importlib.import_module("core.license")
    state_mod = importlib.import_module("core.state")
    monkeypatch.setattr(db_mod, "get_db_pool", AsyncMock(return_value=_FakePool()))
    mod._db_mod = db_mod
    mod._license_mod = license_mod
    mod._state_mod = state_mod
    return mod


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status {self.status_code}", request=None, response=self
            )


class _RoutedFakeClient:
    """Routes GET/POST by exact URL, so one fake drives both the marketplace
    tool lookup and the final plugin-registry execution call."""

    def __init__(self, routes):
        self._routes = routes
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return self._routes[url]

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._routes[url]


def _patch_client(monkeypatch, execution_mod, routes):
    monkeypatch.setattr(
        execution_mod.httpx, "AsyncClient", lambda **k: _RoutedFakeClient(routes)
    )


_TOOL_URL = "http://minder-marketplace:8002/v1/marketplace/ai/tools/get_weather"


def _tool_row(**overrides):
    row = {
        "active": True,
        "plugin_name": "weather",
        "endpoint": "/get_weather",
        "method": "GET",
        "required_tier": "community",
        "parameters": {},
    }
    row.update(overrides)
    return row


# --- tool lookup: not found / inactive ---------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_404_when_tool_not_found(execution_mod, monkeypatch):
    _patch_client(monkeypatch, execution_mod, {_TOOL_URL: _FakeResponse(404)})

    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {})

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_execute_tool_400_when_tool_not_active(execution_mod, monkeypatch):
    _patch_client(
        monkeypatch,
        execution_mod,
        {_TOOL_URL: _FakeResponse(200, _tool_row(active=False))},
    )

    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {})

    assert exc.value.status_code == 400
    assert "not active" in exc.value.detail


# --- license gate -------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_403_when_license_denies_access(execution_mod, monkeypatch):
    _patch_client(
        monkeypatch, execution_mod, {_TOOL_URL: _FakeResponse(200, _tool_row())}
    )

    async def fake_validate(conn, user_id, tool_name):
        return {
            "allowed": False,
            "tier_required": "pro",
            "user_tier": "community",
            "reason": "insufficient tier",
        }

    monkeypatch.setattr(
        execution_mod._license_mod, "validate_tool_access", fake_validate
    )

    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {}, user_id="u1")

    assert exc.value.status_code == 403
    assert exc.value.detail["tier_required"] == "pro"


# --- plugin state gate ---------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_404_when_plugin_not_in_state_db(execution_mod, monkeypatch):
    _patch_client(
        monkeypatch, execution_mod, {_TOOL_URL: _FakeResponse(200, _tool_row())}
    )
    monkeypatch.setattr(
        execution_mod._license_mod,
        "validate_tool_access",
        AsyncMock(return_value={"allowed": True}),
    )
    monkeypatch.setattr(
        execution_mod._state_mod, "get_plugin_state", AsyncMock(return_value=None)
    )

    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {})

    assert exc.value.status_code == 404
    assert "not found in state database" in exc.value.detail


@pytest.mark.asyncio
async def test_execute_tool_400_when_plugin_not_enabled(execution_mod, monkeypatch):
    _patch_client(
        monkeypatch, execution_mod, {_TOOL_URL: _FakeResponse(200, _tool_row())}
    )
    monkeypatch.setattr(
        execution_mod._license_mod,
        "validate_tool_access",
        AsyncMock(return_value={"allowed": True}),
    )
    monkeypatch.setattr(
        execution_mod._state_mod,
        "get_plugin_state",
        AsyncMock(return_value={"state": "disabled"}),
    )

    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {})

    assert exc.value.status_code == 400
    assert "not enabled" in exc.value.detail


# --- parameter validation wired through ---------------------------------------


@pytest.mark.asyncio
async def test_execute_tool_422_on_invalid_parameters(execution_mod, monkeypatch):
    _patch_client(
        monkeypatch,
        execution_mod,
        {
            _TOOL_URL: _FakeResponse(
                200,
                _tool_row(parameters={"city": {"type": "string", "required": True}}),
            )
        },
    )
    monkeypatch.setattr(
        execution_mod._license_mod,
        "validate_tool_access",
        AsyncMock(return_value={"allowed": True}),
    )
    monkeypatch.setattr(
        execution_mod._state_mod,
        "get_plugin_state",
        AsyncMock(return_value={"state": "enabled"}),
    )

    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {})  # missing required 'city'

    assert exc.value.status_code == 422


# --- successful execution: GET and POST dispatch ------------------------------


@pytest.mark.asyncio
async def test_execute_tool_success_via_get(execution_mod, monkeypatch):
    exec_url = "http://minder-plugin-registry:8001/v1/plugins/weather/get_weather"
    routes = {
        _TOOL_URL: _FakeResponse(200, _tool_row(method="GET")),
        exec_url: _FakeResponse(200, {"temp": 72}),
    }
    _patch_client(monkeypatch, execution_mod, routes)
    monkeypatch.setattr(
        execution_mod._license_mod,
        "validate_tool_access",
        AsyncMock(return_value={"allowed": True}),
    )
    monkeypatch.setattr(
        execution_mod._state_mod,
        "get_plugin_state",
        AsyncMock(return_value={"state": "enabled"}),
    )
    monkeypatch.setattr(
        execution_mod.settings,
        "PLUGIN_REGISTRY_URL",
        "http://minder-plugin-registry:8001",
    )

    result = await execution_mod.execute_tool("get_weather", {"city": "Ankara"})

    assert result.tool_name == "get_weather"
    assert result.plugin_name == "weather"
    assert result.result == {"temp": 72}
    assert result.tier_required == "community"


@pytest.mark.asyncio
async def test_execute_tool_success_via_post(execution_mod, monkeypatch):
    exec_url = "http://minder-plugin-registry:8001/v1/plugins/crypto/get_price"
    routes = {
        _TOOL_URL: _FakeResponse(
            200, _tool_row(plugin_name="crypto", endpoint="/get_price", method="POST")
        ),
        exec_url: _FakeResponse(200, {"price": 42}),
    }
    _patch_client(monkeypatch, execution_mod, routes)
    monkeypatch.setattr(
        execution_mod._license_mod,
        "validate_tool_access",
        AsyncMock(return_value={"allowed": True}),
    )
    monkeypatch.setattr(
        execution_mod._state_mod,
        "get_plugin_state",
        AsyncMock(return_value={"state": "enabled"}),
    )
    monkeypatch.setattr(
        execution_mod.settings,
        "PLUGIN_REGISTRY_URL",
        "http://minder-plugin-registry:8001",
    )

    result = await execution_mod.execute_tool("get_weather", {"coin": "btc"})

    assert result.plugin_name == "crypto"
    assert result.result == {"price": 42}


@pytest.mark.asyncio
async def test_execute_tool_param_schema_as_json_string_is_parsed(
    execution_mod, monkeypatch
):
    """parameters_schema round-trips as either a dict or a JSON string
    depending on the marketplace serializer -- confirm the string form is
    decoded before validation, not passed through raw."""
    exec_url = "http://minder-plugin-registry:8001/v1/plugins/weather/get_weather"
    routes = {
        _TOOL_URL: _FakeResponse(
            200,
            _tool_row(
                method="GET",
                parameters='{"city": {"type": "string", "required": true}}',
            ),
        ),
        exec_url: _FakeResponse(200, {"temp": 72}),
    }
    _patch_client(monkeypatch, execution_mod, routes)
    monkeypatch.setattr(
        execution_mod._license_mod,
        "validate_tool_access",
        AsyncMock(return_value={"allowed": True}),
    )
    monkeypatch.setattr(
        execution_mod._state_mod,
        "get_plugin_state",
        AsyncMock(return_value={"state": "enabled"}),
    )
    monkeypatch.setattr(
        execution_mod.settings,
        "PLUGIN_REGISTRY_URL",
        "http://minder-plugin-registry:8001",
    )

    # Missing required 'city' -> still validated correctly against the
    # string-encoded schema, proving it was actually parsed.
    with pytest.raises(HTTPException) as exc:
        await execution_mod.execute_tool("get_weather", {})
    assert exc.value.status_code == 422


# --- discover_tools: tier_filter branch ---------------------------------------


@pytest.mark.asyncio
async def test_discover_tools_forwards_the_tier_filter(execution_mod, monkeypatch):
    captured = {}

    class _FakeDiscoveryClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url, params=None):
            captured["params"] = params
            return _FakeResponse(200, {"tools": []})

    monkeypatch.setattr(
        execution_mod.httpx, "AsyncClient", lambda **k: _FakeDiscoveryClient()
    )

    result = await execution_mod.discover_tools(active_only=True, tier_filter="pro")

    assert captured["params"]["tier"] == "pro"
    assert result.count == 0
