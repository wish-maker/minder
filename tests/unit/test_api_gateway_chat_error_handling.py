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
