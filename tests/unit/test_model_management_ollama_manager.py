"""Unit tests for model-management's OllamaManager (#367).

Covers the real class end-to-end (list/pull/show/delete/test_model +
HTTPException wrapping + the lazy-init guard now delegated to
OllamaClientBase._ensure_initialized), not just a duck-typed stand-in like
test_model_management_error_handling.py uses for the route layer.

Loaded via the same isolated-import pattern as test_model_management_error_handling.py
(core/routes/models/config are collision-prone across services sharing one pytest
process). shared.ai.ollama_client_base is patched directly -- that's where
OllamaManager's inherited initialize() actually looks up AsyncClient/OLLAMA_AVAILABLE.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import shared.ai.ollama_client_base as base_mod

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "model-management"
)

_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    try:
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


def _manager():
    mod = _isolated_import("core.ollama_manager")
    return mod.OllamaManager()


class _FakeAsyncClient:
    def __init__(self, host):
        self.host = host
        self.list = AsyncMock(return_value={"models": [{"name": "llama3.2"}]})
        self.pull = AsyncMock(return_value={"status": "success"})
        self.show = AsyncMock(return_value=MagicMock(model_dump=lambda: {"k": "v"}))
        self.delete = AsyncMock(return_value={"status": "deleted"})
        self.generate = AsyncMock(return_value={"response": "hi"})


@pytest.fixture
def patched_client(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


@pytest.mark.asyncio
async def test_init_does_not_eagerly_connect():
    mgr = _manager()
    assert mgr.client is None
    assert mgr._initialized is False


@pytest.mark.asyncio
async def test_list_models_lazily_initializes_and_returns_models(patched_client):
    mgr = _manager()
    models = await mgr.list_models()
    assert models == [{"name": "llama3.2"}]
    assert mgr._initialized is True
    assert isinstance(mgr.client, patched_client)


@pytest.mark.asyncio
async def test_list_models_does_not_reinitialize_once_ready(patched_client):
    mgr = _manager()
    await mgr.list_models()
    first_client = mgr.client
    await mgr.list_models()
    assert mgr.client is first_client  # same instance -- initialize() ran only once


@pytest.mark.asyncio
async def test_list_models_wraps_failure_as_503(patched_client):
    mgr = _manager()
    await mgr._ensure_initialized()
    mgr.client.list = AsyncMock(side_effect=ConnectionError("unreachable"))
    with pytest.raises(Exception) as exc_info:
        await mgr.list_models()
    assert exc_info.value.status_code == 503
    assert "Failed to list models" in exc_info.value.detail


@pytest.mark.asyncio
async def test_pull_model_success(patched_client):
    mgr = _manager()
    result = await mgr.pull_model("llama3.2:latest")
    assert result == {
        "model": "llama3.2:latest",
        "status": "pulled",
        "details": {"status": "success"},
    }


@pytest.mark.asyncio
async def test_pull_model_wraps_failure_as_503(patched_client):
    mgr = _manager()
    await mgr._ensure_initialized()
    mgr.client.pull = AsyncMock(side_effect=RuntimeError("registry down"))
    with pytest.raises(Exception) as exc_info:
        await mgr.pull_model("llama3.2:latest")
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_show_model_success_normalizes_to_dict(patched_client):
    mgr = _manager()
    result = await mgr.show_model("llama3.2:latest")
    assert result == {"k": "v"}


@pytest.mark.asyncio
async def test_show_model_wraps_genuine_not_found_as_404(patched_client):
    """A real Ollama "model not found" (ResponseError, status_code=404) should
    still surface as 404."""
    mod = _isolated_import("core.ollama_manager")
    mgr = mod.OllamaManager()
    await mgr._ensure_initialized()
    mgr.client.show = AsyncMock(
        side_effect=mod.ResponseError("model not found", status_code=404)
    )
    with pytest.raises(Exception) as exc_info:
        await mgr.show_model("nope:latest")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_show_model_wraps_other_failures_as_503_not_404(patched_client):
    """A transient failure (timeout, connection drop, malformed response) must
    NOT be misreported as "model not found" -- that used to blanket-map every
    exception here to 404, which is indistinguishable from an actually missing
    model and hides a real Ollama outage from the caller."""
    mgr = _manager()
    await mgr._ensure_initialized()
    mgr.client.show = AsyncMock(side_effect=RuntimeError("connection reset"))
    with pytest.raises(Exception) as exc_info:
        await mgr.show_model("llama3.2:latest")
    assert exc_info.value.status_code == 503
    assert "Failed to show model" in exc_info.value.detail


@pytest.mark.asyncio
async def test_delete_model_success(patched_client):
    mgr = _manager()
    result = await mgr.delete_model("llama3.2:latest")
    assert result == {
        "model": "llama3.2:latest",
        "status": "deleted",
        "details": {"status": "deleted"},
    }


@pytest.mark.asyncio
async def test_delete_model_wraps_failure_as_503(patched_client):
    mgr = _manager()
    await mgr._ensure_initialized()
    mgr.client.delete = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(Exception) as exc_info:
        await mgr.delete_model("llama3.2:latest")
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_test_model_success(patched_client):
    mgr = _manager()
    result = await mgr.test_model("llama3.2:latest", prompt="ping")
    assert result == {
        "model": "llama3.2:latest",
        "prompt": "ping",
        "response": "hi",
        "status": "success",
    }


@pytest.mark.asyncio
async def test_test_model_wraps_failure_as_503(patched_client):
    mgr = _manager()
    await mgr._ensure_initialized()
    mgr.client.generate = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(Exception) as exc_info:
        await mgr.test_model("llama3.2:latest")
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_initialize_raises_when_ollama_package_missing(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", False)
    mgr = _manager()
    with pytest.raises(RuntimeError, match="Ollama package not installed"):
        await mgr.list_models()
