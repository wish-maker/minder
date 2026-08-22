"""Unit tests for the api-gateway tool-call argument normalizer (#chat-tools).

Some models (command-r via Ollama) wrap tool arguments in a
``{"tool_name": ..., "parameters": {...}}`` envelope instead of emitting them flat.
Passing that envelope to a plugin action makes the call fail. `_normalize_tool_args`
unwraps it so those models' tool calls actually execute.

api-gateway is a hyphenated service dir; ai.py imports ``from config import settings``
and ``from core.auth import get_current_user_required`` (#613) at module top — fakes
for both are injected and restored.
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
    names = ("config", "core", "core.auth")
    saved = {n: sys.modules.get(n) for n in names}
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(PLUGIN_REGISTRY_URL="http://reg:8001")
    sys.modules["config"] = cfg
    sys.modules["core"] = ModuleType("core")
    fake_core_auth = ModuleType("core.auth")

    async def _fake_get_current_user_required(request):
        return {"sub": "test-user"}

    fake_core_auth.get_current_user_required = _fake_get_current_user_required
    sys.modules["core.auth"] = fake_core_auth
    try:
        spec = importlib.util.spec_from_file_location("ai_under_test", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)


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

    async def fake_get_tool_definitions(owner_user_id=None):
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

    assert result["message"] == {"content": "The price is $42."}
    assert result["minder_tools_offered"] is True
    assert result["minder_tool_calls_made"] == 1
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

    async def fake_get_tool_definitions(owner_user_id=None):
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


def test_parse_content_tool_call_matches_offered_tool(ai_mod):
    meta_by_name = {"get_crypto_price": {"plugin": "crypto"}}
    content = '{"name": "get_crypto_price", "arguments": {"coin": "bitcoin"}}'
    got = ai_mod._parse_content_tool_call(content, meta_by_name)
    assert got == {
        "function": {"name": "get_crypto_price", "arguments": {"coin": "bitcoin"}}
    }


def test_parse_content_tool_call_ignores_unknown_tool_name(ai_mod):
    meta_by_name = {"get_crypto_price": {"plugin": "crypto"}}
    content = '{"name": "delete_everything", "arguments": {}}'
    assert ai_mod._parse_content_tool_call(content, meta_by_name) is None


def test_parse_content_tool_call_ignores_non_json_prose(ai_mod):
    meta_by_name = {"get_crypto_price": {"plugin": "crypto"}}
    assert (
        ai_mod._parse_content_tool_call("Bitcoin is worth $64,000.", meta_by_name)
        is None
    )


def test_parse_content_tool_call_ignores_json_array(ai_mod):
    # Valid JSON, but not an object with "name" -- must not match.
    meta_by_name = {"get_crypto_price": {"plugin": "crypto"}}
    assert ai_mod._parse_content_tool_call("[1, 2, 3]", meta_by_name) is None


def test_parse_content_tool_call_ignores_non_string_content(ai_mod):
    meta_by_name = {"get_crypto_price": {"plugin": "crypto"}}
    assert ai_mod._parse_content_tool_call(None, meta_by_name) is None
    assert ai_mod._parse_content_tool_call(123, meta_by_name) is None


@pytest.mark.asyncio
async def test_chat_with_tools_executes_content_embedded_tool_call(ai_mod, monkeypatch):
    """#250: qwen2.5-coder-style models emit the tool call as JSON content instead
    of native tool_calls. The loop should still recognize + execute it."""
    tool = {
        "type": "function",
        "function": {"name": "get_crypto_price", "parameters": {}},
        "metadata": {
            "plugin": "crypto",
            "endpoint": "/v1/plugins/crypto/actions/get_price",
            "method": "GET",
        },
    }

    async def fake_get_tool_definitions(owner_user_id=None):
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
                "content": (
                    '{"name": "get_crypto_price", "arguments": {"coin": "bitcoin"}}'
                )
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

    assert result["message"] == {"content": "The price is $42."}
    assert result["minder_tools_offered"] is True
    assert result["minder_tool_calls_made"] == 1
    assert len(calls) == 1
    assert calls[0]["params"] == {"coin": "bitcoin"}


@pytest.mark.asyncio
async def test_chat_with_tools_content_not_matching_any_tool_passes_through(
    ai_mod, monkeypatch
):
    """Ordinary prose in content (no matching tool name) returns the response
    unchanged -- no false-positive tool execution. Also the #328 regression
    guard: tools were genuinely offered but never invoked, so
    minder_tool_calls_made must be 0 -- this is the exact silent-hallucination
    shape a live audit caught (a model answering fluently without ever
    calling the real tool, indistinguishable from a real answer without this
    signal)."""
    tool = {
        "type": "function",
        "function": {"name": "get_crypto_price", "parameters": {}},
        "metadata": {"plugin": "crypto", "endpoint": "/x", "method": "GET"},
    }

    async def fake_get_tool_definitions(owner_user_id=None):
        return {"tools": [tool]}

    call_count = 0

    async def fake_call_plugin_tool(*a, **k):
        nonlocal call_count
        call_count += 1
        return {}

    async def fake_ollama_chat(body):
        return {"message": {"content": "Bitcoin is worth about $64,000 right now."}}

    monkeypatch.setattr(ai_mod, "get_tool_definitions", fake_get_tool_definitions)
    monkeypatch.setattr(ai_mod, "_call_plugin_tool", fake_call_plugin_tool)
    monkeypatch.setattr(ai_mod, "_ollama_chat", fake_ollama_chat)

    result = await ai_mod._chat_with_tools(
        {"messages": [{"role": "user", "content": "price of bitcoin?"}]}, None
    )

    assert result["message"] == {"content": "Bitcoin is worth about $64,000 right now."}
    assert result["minder_tools_offered"] is True
    assert result["minder_tool_calls_made"] == 0
    assert call_count == 0
