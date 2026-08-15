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

core.execution also does a bare `from config import settings` -- "config" is
just as collision-prone across this shared pytest process as "core"/"models"
(every service has its own config.py, all competing for the same bare module
name). This loads plugin-state-manager's own config.py fresh from its file and
registers *that* under "config" for the duration of the fixture, instead of a
bare `import config` left to whatever ambient sys.path order some other
already-run test happened to leave behind.
"""

import importlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_PSM = Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"
_COLLISION_PRONE = (
    "core",
    "core.execution",
    "models",
    "models.tool_execution",
    "config",
)


@pytest.fixture
def execution_mod():
    saved_path = list(sys.path)
    saved_modules = {k: sys.modules[k] for k in _COLLISION_PRONE if k in sys.modules}
    for k in _COLLISION_PRONE:
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_PSM))
    config_spec = importlib.util.spec_from_file_location("config", _PSM / "config.py")
    config_mod = importlib.util.module_from_spec(config_spec)
    sys.modules["config"] = config_mod
    config_spec.loader.exec_module(config_mod)
    try:
        yield importlib.import_module("core.execution")
    finally:
        sys.path[:] = saved_path
        for k in _COLLISION_PRONE:
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


class _FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def raise_for_status(self):
        pass

    def json(self):
        return self._json


class _FakeAsyncClient:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self._status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        return _FakeResponse(self._json, status_code=self._status_code)


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


# ── _validate_parameters (#676) ─────────────────────────────────────────────
# execute_tool forwarded every caller-supplied parameter to the downstream
# plugin action verbatim, never checking it against the tool's own declared
# schema (already fetched from marketplace but unused for this). These test
# the pure validator directly -- no need to go through execute_tool's
# DB/license-gated lazy imports (see this file's own docstring on why that's
# excluded from this harness).


def _schema(execution_mod, **param_overrides):
    row = _tool_row(parameters={"symbol": {"type": "string", "description": "x"}})
    row["parameters"].update(param_overrides)
    return execution_mod._row_to_tool_schema(row)


def test_validate_parameters_passes_when_all_required_present_and_typed(
    execution_mod,
):
    schema = _schema(
        execution_mod,
        symbol={"type": "string", "description": "x", "required": True},
    )
    execution_mod._validate_parameters(schema, {"symbol": "BTC"})  # no raise


def test_validate_parameters_rejects_missing_required_field(execution_mod):
    schema = _schema(
        execution_mod,
        symbol={"type": "string", "description": "x", "required": True},
    )
    with pytest.raises(Exception) as exc_info:
        execution_mod._validate_parameters(schema, {})
    assert exc_info.value.status_code == 422
    assert any("'symbol' is required" in e for e in exc_info.value.detail)


def test_validate_parameters_permissive_on_missing_optional_field(execution_mod):
    schema = _schema(
        execution_mod,
        symbol={"type": "string", "description": "x", "required": False},
    )
    execution_mod._validate_parameters(schema, {})  # no raise


def test_validate_parameters_rejects_wrong_type(execution_mod):
    schema = _schema(execution_mod, count={"type": "integer", "description": "x"})
    with pytest.raises(Exception) as exc_info:
        execution_mod._validate_parameters(schema, {"count": "not-a-number"})
    assert exc_info.value.status_code == 422
    assert any("must be of type integer" in e for e in exc_info.value.detail)


def test_validate_parameters_bool_does_not_satisfy_integer_type(execution_mod):
    """bool is a subclass of int in Python -- must not be silently accepted for
    a declared "integer"/"number" parameter."""
    schema = _schema(execution_mod, count={"type": "integer", "description": "x"})
    with pytest.raises(Exception) as exc_info:
        execution_mod._validate_parameters(schema, {"count": True})
    assert exc_info.value.status_code == 422
    assert any("got boolean" in e for e in exc_info.value.detail)


def test_validate_parameters_rejects_enum_violation(execution_mod):
    schema = _schema(
        execution_mod,
        unit={"type": "string", "description": "x", "enum": ["celsius", "fahrenheit"]},
    )
    with pytest.raises(Exception) as exc_info:
        execution_mod._validate_parameters(schema, {"unit": "kelvin"})
    assert exc_info.value.status_code == 422
    assert any("must be one of" in e for e in exc_info.value.detail)


def test_validate_parameters_permissive_on_undeclared_extra_keys(execution_mod):
    """Some plugin actions accept optional untyped kwargs -- a schema isn't
    necessarily exhaustive, so an undeclared key must not be rejected."""
    schema = _schema(execution_mod, symbol={"type": "string", "description": "x"})
    execution_mod._validate_parameters(
        schema, {"symbol": "BTC", "extra_untyped_kwarg": "anything"}
    )  # no raise


def test_validate_parameters_skips_type_check_for_unrecognised_type(execution_mod):
    """Schemas are marketplace-authored, not a fixed enum of `type` strings --
    an unrecognised type must not crash or block the call, just skip the type
    check for that field."""
    schema = _schema(
        execution_mod, thing={"type": "some-custom-type", "description": "x"}
    )
    execution_mod._validate_parameters(schema, {"thing": object()})  # no raise


def test_validate_parameters_collects_multiple_violations_at_once(execution_mod):
    schema = _schema(
        execution_mod,
        symbol={"type": "string", "description": "x", "required": True},
        count={"type": "integer", "description": "x"},
    )
    with pytest.raises(Exception) as exc_info:
        execution_mod._validate_parameters(schema, {"count": "nope"})
    assert len(exc_info.value.detail) == 2


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


@pytest.mark.asyncio
async def test_discover_plugin_tools_unknown_plugin_404_not_500(
    monkeypatch, execution_mod
):
    """#576: a plugin absent from the catalog makes marketplace return 404. That
    must surface as a clean 404, not a 500 (raise_for_status used to bubble an
    httpx error into the route's generic handler → sanitized 500 for EVERY
    unknown plugin)."""
    from fastapi import HTTPException

    monkeypatch.setattr(
        execution_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient({}, status_code=404),
    )
    with pytest.raises(HTTPException) as exc:
        await execution_mod.discover_plugin_tools(
            "00000000-0000-0000-0000-000000000000"
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Plugin not found"
