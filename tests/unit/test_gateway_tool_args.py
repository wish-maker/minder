"""Unit tests for the api-gateway tool-call argument normalizer (#chat-tools).

Some models (command-r via Ollama) wrap tool arguments in a
``{"tool_name": ..., "parameters": {...}}`` envelope instead of emitting them flat.
Passing that envelope to a plugin action makes the call fail. `_normalize_tool_args`
unwraps it so those models' tool calls actually execute.

api-gateway is a hyphenated service dir; ai.py imports ``from config import settings``
at module top — a fake config is injected and restored.
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
        spec = importlib.util.spec_from_file_location("ai_under_test", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_unwraps_parameters_envelope(ai_mod):
    # command-r's shape → the flat args the plugin expects.
    got = ai_mod._normalize_tool_args(
        {"tool_name": "get_crypto_price", "parameters": {"coin": "bitcoin"}}
    )
    assert got == {"coin": "bitcoin"}


def test_bare_parameters_envelope(ai_mod):
    assert ai_mod._normalize_tool_args({"parameters": {"coin": "eth"}}) == {
        "coin": "eth"
    }


def test_flat_args_unchanged(ai_mod):
    assert ai_mod._normalize_tool_args({"coin": "bitcoin"}) == {"coin": "bitcoin"}


def test_non_dict_becomes_empty(ai_mod):
    assert ai_mod._normalize_tool_args(None) == {}
    assert ai_mod._normalize_tool_args("nope") == {}


def test_non_dict_parameters_left_alone(ai_mod):
    # "parameters" that isn't a dict is a real arg, not an envelope — keep as-is.
    args = {"parameters": "raw", "coin": "eth"}
    assert ai_mod._normalize_tool_args(args) == args


@pytest.mark.asyncio
async def test_chat_with_tools_routes_get_tool_args_as_params(ai_mod, monkeypatch):
    """#254: a GET-method tool's args must go through as query params, not a JSON
    body -- _call_plugin_tool branches on metadata["method"], but the call site in
    _chat_with_tools has to route args to the right kwarg for that branch to matter."""
    tool = {
        "type": "function",
        "function": {"name": "get_crypto_price", "parameters": {}},
        "metadata": {
            "plugin": "crypto",
            "endpoint": "/v1/plugins/crypto/actions/get_price",
            "method": "GET",
        },
    }

    async def fake_get_tool_definitions():
        return {"tools": [tool]}

    calls = []

    async def fake_call_plugin_tool(
        metadata, *, json_body=None, params=None, auth_header=None
    ):
        calls.append({"json_body": json_body, "params": params})
        return {"coin": "bitcoin", "price": 42}

    responses = [
        {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "get_crypto_price",
                            "arguments": {"coin": "bitcoin"},
                        }
                    }
                ]
            }
        },
        {"message": {"content": "The price is $42."}},
    ]

    async def fake_ollama_chat(body):
        return responses.pop(0)

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)
    monkeypatch.setattr(ai_mod, "_ollama_chat", fake_ollama_chat)

    result = await ai_mod._chat_with_tools(
        {"messages": [{"role": "user", "content": "price of bitcoin?"}]}, None
    )

    assert result == {"message": {"content": "The price is $42."}}
    assert len(calls) == 1
    assert calls[0]["params"] == {"coin": "bitcoin"}
    assert calls[0]["json_body"] is None


@pytest.mark.asyncio
async def test_chat_with_tools_routes_post_tool_args_as_json_body(ai_mod, monkeypatch):
    """A POST-method (default) tool keeps going through json_body, unchanged."""
    tool = {
        "type": "function",
        "function": {"name": "refresh_crypto", "parameters": {}},
        "metadata": {
            "plugin": "crypto",
            "endpoint": "/v1/plugins/crypto/actions/refresh",
            "method": "POST",
        },
    }

    async def fake_get_tool_definitions():
        return {"tools": [tool]}

    calls = []

    async def fake_call_plugin_tool(
        metadata, *, json_body=None, params=None, auth_header=None
    ):
        calls.append({"json_body": json_body, "params": params})
        return {"refreshed": True}

    responses = [
        {
            "message": {
                "tool_calls": [
                    {"function": {"name": "refresh_crypto", "arguments": {}}}
                ]
            }
        },
        {"message": {"content": "Done."}},
    ]

    async def fake_ollama_chat(body):
        return responses.pop(0)

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)
    monkeypatch.setattr(ai_mod, "_ollama_chat", fake_ollama_chat)

    await ai_mod._chat_with_tools(
        {"messages": [{"role": "user", "content": "refresh crypto"}]}, None
    )

    assert len(calls) == 1
    assert calls[0]["json_body"] == {}
    assert calls[0]["params"] is None
