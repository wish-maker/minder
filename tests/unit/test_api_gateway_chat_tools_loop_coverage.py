"""Unit tests filling routes/ai.py's remaining coverage gaps (82%).

test_api_gateway_chat_error_handling.py and test_gateway_ai_tool_functions.py
mock _ollama_chat/_chat_with_tools out WHOLESALE in every test -- neither
function's own internal logic (the actual httpx call + Ollama 4xx/5xx
handling in _ollama_chat, and the tool-calling loop's stream/no-tools
shortcuts, unknown-tool branch, HTTPStatusError/generic-exception branches,
and iterations-exhausted final answer in _chat_with_tools) had ever executed.

Same _isolated_import pattern as test_api_gateway_chat_error_handling.py.
httpx.AsyncClient is monkeypatched to build a real client over an
httpx.MockTransport (matches this session's established convention) so
_ollama_chat exercises real request/response plumbing without a live Ollama.
"""

import sys
from pathlib import Path

import httpx
import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "api-gateway"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config", "middleware")


def _isolated_import(module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")

    import importlib

    try:
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


ai = _isolated_import("routes.ai")

_RealAsyncClient = httpx.AsyncClient


def _mock_client(handler):
    return lambda **kwargs: _RealAsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://fake"
    )


# ── _ollama_chat ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ollama_chat_returns_json_on_success(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={"message": {"content": "hi"}})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    result = await ai._ollama_chat({"messages": []})

    assert result == {"message": {"content": "hi"}}


@pytest.mark.asyncio
async def test_ollama_chat_forces_stream_false(monkeypatch):
    captured = {}

    def handler(request):
        import json as json_mod

        captured["payload"] = json_mod.loads(request.content)
        return httpx.Response(200, json={"message": {}})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    await ai._ollama_chat({"messages": [], "stream": True})

    assert captured["payload"]["stream"] is False


@pytest.mark.asyncio
async def test_ollama_chat_4xx_with_structured_error_surfaces_ollamas_message(
    monkeypatch,
):
    def handler(request):
        return httpx.Response(404, json={"error": "model 'nope' not found"})

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    with pytest.raises(ai.HTTPException) as exc_info:
        await ai._ollama_chat({"model": "nope", "messages": []})

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "model 'nope' not found"


@pytest.mark.asyncio
async def test_ollama_chat_4xx_without_parseable_error_uses_generic_detail(
    monkeypatch,
):
    def handler(request):
        return httpx.Response(400, text="not json")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    with pytest.raises(ai.HTTPException) as exc_info:
        await ai._ollama_chat({"messages": []})

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Ollama rejected the request"


@pytest.mark.asyncio
async def test_ollama_chat_5xx_raises_http_status_error(monkeypatch):
    def handler(request):
        return httpx.Response(500, text="internal error")

    monkeypatch.setattr(httpx, "AsyncClient", _mock_client(handler))

    with pytest.raises(httpx.HTTPStatusError):
        await ai._ollama_chat({"messages": []})


# ── _chat_with_tools: shortcuts ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_with_tools_streaming_request_bypasses_the_tool_loop(monkeypatch):
    async def fake_ollama_chat(body):
        return {"message": {"content": "streamed"}}

    monkeypatch.setattr(ai, "_ollama_chat", fake_ollama_chat)

    result = await ai._chat_with_tools({"messages": [], "stream": True}, None)

    assert result["message"]["content"] == "streamed"
    assert result["minder_tools_offered"] is False
    assert result["minder_tool_calls_made"] == 0


@pytest.mark.asyncio
async def test_chat_with_tools_no_tools_available_bypasses_the_tool_loop(monkeypatch):
    async def fake_ollama_chat(body):
        return {"message": {"content": "no tools"}}

    async def fake_defs():
        return {"tools": []}

    monkeypatch.setattr(ai, "_ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(ai, "get_tool_definitions", fake_defs)

    result = await ai._chat_with_tools({"messages": []}, None)

    assert result["minder_tools_offered"] is False
    assert result["minder_tool_calls_made"] == 0


# ── _chat_with_tools: the tool-calling loop itself ────────────────────────────

_ONE_TOOL = {
    "type": "function",
    "function": {"name": "get_price", "description": "d", "parameters": {}},
    "metadata": {"endpoint": "http://plugin/price", "method": "POST"},
}


def _fake_defs_with_one_tool():
    async def fake_defs():
        return {"tools": [_ONE_TOOL]}

    return fake_defs


@pytest.mark.asyncio
async def test_chat_with_tools_unknown_tool_name_feeds_back_an_error(monkeypatch):
    calls = {"n": 0}

    async def fake_ollama_chat(body):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "nonexistent", "arguments": {}}}
                    ]
                }
            }
        return {"message": {"content": "done"}}

    monkeypatch.setattr(ai, "_ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(ai, "get_tool_definitions", _fake_defs_with_one_tool())

    result = await ai._chat_with_tools({"messages": []}, None)

    assert result["message"]["content"] == "done"
    assert result["minder_tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_chat_with_tools_401_from_tool_appends_auth_hint(monkeypatch):
    calls = {"n": 0}

    async def fake_ollama_chat(body):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "message": {
                    "tool_calls": [{"function": {"name": "get_price", "arguments": {}}}]
                }
            }
        return {"message": {"content": "done"}}

    async def fake_call_plugin_tool(meta, json_body, params, auth_header):
        request = httpx.Request("POST", "http://plugin/price")
        raise httpx.HTTPStatusError(
            "401", request=request, response=httpx.Response(401, text="unauthorized")
        )

    monkeypatch.setattr(ai, "get_tool_definitions", _fake_defs_with_one_tool())
    monkeypatch.setattr(ai, "_call_plugin_tool", fake_call_plugin_tool)

    # Capture the tool-result message fed back on the SECOND call.
    seen_messages = []

    async def fake_ollama_chat_capturing(body):
        seen_messages.append(list(body.get("messages", [])))
        return await fake_ollama_chat(body)

    monkeypatch.setattr(ai, "_ollama_chat", fake_ollama_chat_capturing)

    result = await ai._chat_with_tools({"messages": []}, None)

    assert result["message"]["content"] == "done"
    tool_message = seen_messages[-1][-1]
    assert tool_message["role"] == "tool"
    assert "HTTP 401" in tool_message["content"]
    assert "authentication required" in tool_message["content"]


@pytest.mark.asyncio
async def test_chat_with_tools_generic_tool_exception_feeds_back_an_error(monkeypatch):
    calls = {"n": 0}

    async def fake_ollama_chat(body):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "message": {
                    "tool_calls": [{"function": {"name": "get_price", "arguments": {}}}]
                }
            }
        return {"message": {"content": "done"}}

    async def fake_call_plugin_tool(meta, json_body, params, auth_header):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(ai, "_ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(ai, "get_tool_definitions", _fake_defs_with_one_tool())
    monkeypatch.setattr(ai, "_call_plugin_tool", fake_call_plugin_tool)

    result = await ai._chat_with_tools({"messages": []}, None)

    assert result["message"]["content"] == "done"
    assert result["minder_tool_calls_made"] == 1


@pytest.mark.asyncio
async def test_chat_with_tools_exhausts_iterations_and_returns_final_answer(
    monkeypatch,
):
    async def always_calls_a_tool(body):
        return {
            "message": {
                "tool_calls": [{"function": {"name": "get_price", "arguments": {}}}]
            }
        }

    async def fake_call_plugin_tool(meta, json_body, params, auth_header):
        return {"price": 42}

    calls = {"n": 0}

    async def fake_ollama_chat(body):
        calls["n"] += 1
        if calls["n"] > ai.MAX_TOOL_ITERATIONS:
            return {"message": {"content": "final answer, no more tools"}}
        return await always_calls_a_tool(body)

    monkeypatch.setattr(ai, "_ollama_chat", fake_ollama_chat)
    monkeypatch.setattr(ai, "get_tool_definitions", _fake_defs_with_one_tool())
    monkeypatch.setattr(ai, "_call_plugin_tool", fake_call_plugin_tool)

    result = await ai._chat_with_tools({"messages": []}, None)

    assert result["message"]["content"] == "final answer, no more tools"
    assert result["minder_tools_offered"] is True
    assert result["minder_tool_calls_made"] == ai.MAX_TOOL_ITERATIONS
    # MAX_TOOL_ITERATIONS loop calls + 1 final call, no more.
    assert calls["n"] == ai.MAX_TOOL_ITERATIONS + 1
