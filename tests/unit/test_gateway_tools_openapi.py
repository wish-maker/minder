"""Unit tests for the api-gateway OpenAPI tool-server endpoint (#251).

GET /v1/ai/tools/openapi.json exposes Minder's read-only plugin tools as an
OpenAPI 3.x spec, consumable directly by OpenWebUI as a "Tool Server" (Settings
-> Admin -> Tool Servers, type "openapi"). It must mirror get_tool_definitions()
dynamically and MUST exclude any tool whose declared method isn't GET -- anything
present here becomes freely callable with no further per-request auth once an
admin connects it, so mutating/admin actions must never leak in.

api-gateway is a hyphenated service dir; ai.py imports ``from config import
settings`` at module top — a fake config is injected and restored, matching
test_gateway_tool_args.py's precedent.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "ai.py"
)


@pytest.fixture
def ai_mod():
    saved = sys.modules.get("config")
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(PLUGIN_REGISTRY_URL="http://reg:8001")
    sys.modules["config"] = cfg
    try:
        spec = importlib.util.spec_from_file_location("ai_under_test_openapi", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def _tool(name, endpoint, method, parameters=None, required=None, description=""):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": parameters or {},
                "required": required or [],
            },
        },
        "metadata": {"plugin": "x", "endpoint": endpoint, "method": method},
    }


@pytest.mark.asyncio
async def test_spec_includes_get_tools_with_query_params(ai_mod, monkeypatch):
    tool = _tool(
        "get_crypto_price",
        "/v1/plugins/crypto/actions/get_price",
        "GET",
        parameters={"coin": {"type": "string", "description": "Coin symbol"}},
        required=["coin"],
        description="Get the latest crypto price.",
    )

    async def fake_get_tool_definitions():
        return {"tools": [tool]}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)

    spec = await ai_mod.tools_openapi_spec()

    assert spec["openapi"] == "3.1.0"
    assert spec["servers"] == [{"url": "http://reg:8001"}]
    path = spec["paths"]["/v1/plugins/crypto/actions/get_price"]
    op = path["get"]
    assert op["operationId"] == "get_crypto_price"
    assert op["description"] == "Get the latest crypto price."
    assert op["parameters"] == [
        {
            "name": "coin",
            "in": "query",
            "required": True,
            "schema": {"type": "string"},
            "description": "Coin symbol",
        }
    ]


@pytest.mark.asyncio
async def test_spec_excludes_post_only_tools(ai_mod, monkeypatch):
    """A tool with no declared method (defaults POST) or an explicit POST method
    must NEVER appear -- this is the security boundary (#254 split)."""
    get_tool = _tool("get_weather", "/v1/plugins/weather/actions/get_weather", "GET")
    post_tool = _tool("refresh_crypto", "/v1/plugins/crypto/actions/refresh", "POST")
    default_method_tool = {
        "type": "function",
        "function": {"name": "delete_everything", "parameters": {}},
        "metadata": {"plugin": "x", "endpoint": "/v1/plugins/x/actions/wipe"},
    }

    async def fake_get_tool_definitions():
        return {"tools": [get_tool, post_tool, default_method_tool]}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)

    spec = await ai_mod.tools_openapi_spec()

    assert list(spec["paths"].keys()) == ["/v1/plugins/weather/actions/get_weather"]


@pytest.mark.asyncio
async def test_spec_empty_when_no_tools(ai_mod, monkeypatch):
    async def fake_get_tool_definitions():
        return {"tools": []}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)

    spec = await ai_mod.tools_openapi_spec()

    assert spec["paths"] == {}


@pytest.mark.asyncio
async def test_spec_skips_tool_missing_endpoint(ai_mod, monkeypatch):
    broken_tool = {
        "type": "function",
        "function": {"name": "no_endpoint_tool", "parameters": {}},
        "metadata": {"plugin": "x", "method": "GET"},  # no "endpoint" key
    }

    async def fake_get_tool_definitions():
        return {"tools": [broken_tool]}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)

    spec = await ai_mod.tools_openapi_spec()

    assert spec["paths"] == {}


@pytest.mark.asyncio
async def test_spec_multiple_params_and_optional_field(ai_mod, monkeypatch):
    tool = _tool(
        "get_news",
        "/v1/plugins/news/actions/get_news",
        "GET",
        parameters={
            "feed": {"type": "string", "description": "Feed name"},
            "limit": {"type": "integer", "description": "Max headlines"},
        },
        required=[],  # both optional
        description="Get latest headlines.",
    )

    async def fake_get_tool_definitions():
        return {"tools": [tool]}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)

    spec = await ai_mod.tools_openapi_spec()

    params = {
        p["name"]: p
        for p in spec["paths"]["/v1/plugins/news/actions/get_news"]["get"]["parameters"]
    }
    assert params["feed"]["required"] is False
    assert params["limit"]["schema"]["type"] == "integer"
    assert params["limit"]["required"] is False
