"""Unit tests for plugin-state-manager's tool discovery (core/execution.py).

discover_tools/discover_plugin_tools had zero direct tests. Both defensively
parse `parameters`/`response_format` as EITHER a dict already OR a JSON string
that needs `json.loads` first (the marketplace API can return either, depending
on how the row was stored) -- that branch was entirely unexercised.

execute_tool (same file) is deliberately NOT tested end-to-end here: it does
`from core.database import get_db_pool` / `from core.license import
validate_tool_access` / `from core.state import get_plugin_state` as LAZY
imports inside the function body, the same pattern
test_marketplace_error_handling.py already documented as too fragile for this
harness's isolated-import convention to reliably mock across the full suite.
Its execution-URL construction (previously missing a `/v1` prefix, 404ing
against the real plugin-registry) was pulled out into the pure
`_build_execution_url` helper specifically so THAT part is still testable.

plugin-state-manager is a hyphenated service dir, so core.execution is loaded
by path, same isolated-import pattern as test_psm_state_transitions.py /
test_psm_license.py.
"""

import importlib
import json
import sys
from pathlib import Path

import pytest

_PSM = Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"
_COLLISION_PRONE = ("core", "core.execution", "models", "models.tool_execution")


@pytest.fixture
def execution_mod():
    saved_path = list(sys.path)
    saved_modules = {k: sys.modules[k] for k in _COLLISION_PRONE if k in sys.modules}
    for k in _COLLISION_PRONE:
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_PSM))
    try:
        yield importlib.import_module("core.execution")
    finally:
        sys.path[:] = saved_path
        for k in _COLLISION_PRONE:
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


class _FakeResponse:
    def __init__(self, json_data):
        self._json = json_data

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, json_data):
        self._json = json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        return _FakeResponse(self._json)


def _tool_row(**overrides):
    row = {
        "tool_name": "crypto_price",
        "description": "Get the current price of a crypto asset",
        "type": "data",
        "parameters": {"symbol": {"type": "string", "description": "ticker symbol"}},
        "response_format": {"price": {"type": "number", "description": "USD price"}},
        "endpoint": "/price",
        "method": "GET",
        "required_tier": "community",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_discover_tools_parses_dict_parameters_directly(
    monkeypatch, execution_mod
):
    monkeypatch.setattr(
        execution_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient({"tools": [_tool_row()]}),
    )
    result = await execution_mod.discover_tools()
    assert result.count == 1
    assert result.tools[0].name == "crypto_price"
    assert result.tools[0].parameters["symbol"].type == "string"


@pytest.mark.asyncio
async def test_discover_tools_parses_json_string_parameters(monkeypatch, execution_mod):
    """The marketplace can return parameters/response_format as a JSON-encoded
    string instead of an already-parsed dict -- both branches must work."""
    row = _tool_row(
        parameters=json.dumps(
            {"symbol": {"type": "string", "description": "ticker symbol"}}
        ),
        response_format=json.dumps(
            {"price": {"type": "number", "description": "USD price"}}
        ),
    )
    monkeypatch.setattr(
        execution_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient({"tools": [row]}),
    )
    result = await execution_mod.discover_tools()
    assert result.count == 1
    assert result.tools[0].parameters["symbol"].type == "string"
    assert result.tools[0].response_format == {
        "price": {"type": "number", "description": "USD price"}
    }


@pytest.mark.asyncio
async def test_discover_tools_empty_result(monkeypatch, execution_mod):
    monkeypatch.setattr(
        execution_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient({"tools": []}),
    )
    result = await execution_mod.discover_tools()
    assert result.count == 0
    assert result.tools == []


def test_build_execution_url_adds_v1_prefix(execution_mod):
    """Regression guard: execution_url used to be built as
    f"{registry_url}/plugins/{name}{endpoint}" (missing /v1), which 404'd
    against the real plugin-registry -- its actions route is versioned
    (`/v1/plugins/{name}/actions/{action}`). `tool_endpoint` (marketplace's
    `endpoint_path`) is a relative path like "/actions/get_weather"."""
    url = execution_mod._build_execution_url(
        "http://minder-plugin-registry:8001", "weather", "/actions/get_weather"
    )
    assert (
        url
        == "http://minder-plugin-registry:8001/v1/plugins/weather/actions/get_weather"
    )


@pytest.mark.asyncio
async def test_discover_plugin_tools_parses_json_string_parameters(
    monkeypatch, execution_mod
):
    row = _tool_row(
        parameters=json.dumps(
            {"symbol": {"type": "string", "description": "ticker symbol"}}
        )
    )
    monkeypatch.setattr(
        execution_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient({"tools": [row]}),
    )
    result = await execution_mod.discover_plugin_tools("some-plugin-id")
    assert result.count == 1
    assert result.tools[0].parameters["symbol"].type == "string"
