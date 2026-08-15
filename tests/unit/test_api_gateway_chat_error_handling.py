"""Unit test for api-gateway's chat_completions error handling (#357).

#357: both the plain and tool-augmented-fallback paths caught a generic
Exception and returned HTTPException(502, detail=f"Chat failed: {str(e)}") --
leaking the raw Ollama/httpx exception string. Switched to
shared.errors.backend_http_error.

Loaded via sys.path + a stale-cache clear (conftest.py loads every service's
main.py into ONE shared pytest process) -- matching this session's
established precedent. chat_completions is a plain module-level function
(not built via a router factory), so it's tested by monkeypatching the
module-level _ollama_chat helper directly.
"""

import sys
from pathlib import Path

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


class _FakeRequest:
    def __init__(self, body: dict):
        self._body = body

    async def json(self):
        return dict(self._body)


@pytest.mark.asyncio
async def test_plain_chat_failure_does_not_leak_exception_text(monkeypatch):
    secret_looking = "internal ollama token=abc123"

    async def boom(body):
        raise ConnectionError(secret_looking)

    monkeypatch.setattr(ai, "_ollama_chat", boom)

    with pytest.raises(Exception) as exc_info:
        await ai.chat_completions(_FakeRequest({"messages": []}))

    assert exc_info.value.status_code == 503
    assert secret_looking not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_tool_augmented_fallback_failure_does_not_leak_exception_text(
    monkeypatch,
):
    secret_looking = "internal ollama token=abc123"

    async def boom_tools(body, auth_header):
        raise RuntimeError("tool path broke")

    async def boom_plain(body):
        raise ConnectionError(secret_looking)

    monkeypatch.setattr(ai, "_chat_with_tools", boom_tools)
    monkeypatch.setattr(ai, "_ollama_chat", boom_plain)

    with pytest.raises(Exception) as exc_info:
        await ai.chat_completions(_FakeRequest({"messages": [], "minder_tools": True}))

    assert exc_info.value.status_code == 503
    assert secret_looking not in str(exc_info.value.detail)


# ── #578: a clean 4xx from Ollama (e.g. unknown model) must NOT become a 500 ──


@pytest.mark.asyncio
async def test_plain_chat_unknown_model_4xx_surfaces_not_500(monkeypatch):
    from fastapi import HTTPException

    async def model_not_found(body):
        raise HTTPException(status_code=404, detail="model 'nope' not found")

    monkeypatch.setattr(ai, "_ollama_chat", model_not_found)

    with pytest.raises(HTTPException) as exc_info:
        await ai.chat_completions(_FakeRequest({"model": "nope", "messages": []}))

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "model 'nope' not found"


@pytest.mark.asyncio
async def test_tool_path_unknown_model_4xx_surfaces_via_fallback(monkeypatch):
    from fastapi import HTTPException

    async def boom_tools(body, auth_header):
        # the tools call itself hit the unknown model
        raise HTTPException(status_code=404, detail="model 'nope' not found")

    async def plain_model_not_found(body):
        raise HTTPException(status_code=404, detail="model 'nope' not found")

    monkeypatch.setattr(ai, "_chat_with_tools", boom_tools)
    monkeypatch.setattr(ai, "_ollama_chat", plain_model_not_found)

    with pytest.raises(HTTPException) as exc_info:
        await ai.chat_completions(
            _FakeRequest({"model": "nope", "messages": [], "minder_tools": True})
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_tool_failure_still_falls_back_to_working_plain_chat(monkeypatch):
    # A tool-path failure (e.g. the model doesn't support tools) must still fall back
    # to a plain passthrough that succeeds — the #578 re-raise must not break this.
    async def boom_tools(body, auth_header):
        raise RuntimeError("model does not support tools")

    async def plain_ok(body):
        return {"message": {"content": "hello from plain chat"}}

    monkeypatch.setattr(ai, "_chat_with_tools", boom_tools)
    monkeypatch.setattr(ai, "_ollama_chat", plain_ok)

    result = await ai.chat_completions(
        _FakeRequest({"model": "llama3.2", "messages": [], "minder_tools": True}),
        current_user={"sub": "u1"},
    )
    assert result == {"message": {"content": "hello from plain chat"}}


# ── #613: chat/completions must require a valid JWT — every other route in this
# module either serves pure read-only tool-discovery metadata (deliberately public
# for OpenWebUI's Tool Server integration, which has no way to attach a Minder JWT)
# or proxies to a downstream endpoint that enforces its own auth; this one calls
# Ollama directly with nothing else in the request path to gate it. Exercised
# through a REAL FastAPI TestClient (not a direct function call, which would bypass
# dependency injection entirely) so the Depends(...) wiring itself is proven, not
# just the handler body.


def _ai_router_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(ai.router)
    return TestClient(app, raise_server_exceptions=False)


def test_chat_completions_requires_auth():
    client = _ai_router_client()
    resp = client.post("/v1/ai/chat/completions", json={"messages": []})
    assert resp.status_code == 401


def test_chat_completions_succeeds_with_a_valid_token(monkeypatch):
    async def plain_ok(body):
        return {"message": {"content": "hi"}}

    monkeypatch.setattr(ai, "_ollama_chat", plain_ok)
    client = _ai_router_client()
    client.app.dependency_overrides[ai.get_current_user_required] = lambda: {
        "sub": "u1"
    }

    resp = client.post(
        "/v1/ai/chat/completions",
        json={"messages": []},
        headers={"Authorization": "Bearer whatever"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"message": {"content": "hi"}}


def test_functions_definitions_stays_open_for_openwebui_tool_server(monkeypatch):
    """Deliberately NOT gated (#613) -- OpenWebUI's Tool Server integration has no
    way to attach a Minder JWT, so this read-only discovery endpoint must stay
    reachable without one."""

    async def fake_defs():
        return {"tools": []}

    monkeypatch.setattr(ai, "get_tool_definitions", fake_defs)
    client = _ai_router_client()

    resp = client.get("/v1/ai/functions/definitions")
    assert resp.status_code == 200
