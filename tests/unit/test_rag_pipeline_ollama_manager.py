"""Unit tests for rag-pipeline's OllamaManager (#367).

Covers the real class end-to-end (the embed_client + connection-test
_post_connect hook, ensure_model, generate_embeddings, generate_response, and
the lazy-init guard now delegated to OllamaClientBase._ensure_initialized) --
test_rag_ollama_failover_error.py only covers the module-level
_describe_failover_404 function, not the class itself.

Loaded the same way as that file (a bare `from config import ...` at module
level collides with sibling services' own config.py across one pytest
process, so this force-loads THIS service's config.py under that name first).

Because `rag/ollama_manager.py` does `from shared.ai.ollama_client_base import
AsyncClient`, that name is copied into ITS OWN module namespace at import time
-- patching shared.ai.ollama_client_base.AsyncClient alone would not affect
`_post_connect`'s `AsyncClient(host=...)` call, which resolves via the loaded
module's own namespace. Both are patched together via `patched_client` below.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

import shared.ai.ollama_client_base as base_mod

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "rag-pipeline"


def _load_ollama_manager():
    config_spec = importlib.util.spec_from_file_location(
        "config", _SERVICE_DIR / "config.py"
    )
    config_mod = importlib.util.module_from_spec(config_spec)
    sys.modules["config"] = config_mod
    config_spec.loader.exec_module(config_mod)

    spec = importlib.util.spec_from_file_location(
        "rag_pipeline_ollama_manager_full", _SERVICE_DIR / "rag" / "ollama_manager.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rag_pipeline_ollama_manager_full"] = mod
    spec.loader.exec_module(mod)
    return mod


_mod = _load_ollama_manager()


class _FakeAsyncClient:
    def __init__(self, host):
        self.host = host
        self.list = AsyncMock(return_value={"models": [{"name": "llama3.2:latest"}]})
        self.pull = AsyncMock(return_value=None)
        self.embeddings = AsyncMock(return_value={"embedding": [0.1, 0.2, 0.3]})
        self.generate = AsyncMock(
            return_value={"response": "hi", "prompt_eval_count": 3, "eval_count": 5}
        )


@pytest.fixture
def patched_client(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    monkeypatch.setattr(_mod, "AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


def _manager():
    return _mod.OllamaManager()


@pytest.mark.asyncio
async def test_init_does_not_eagerly_connect():
    mgr = _manager()
    assert mgr.client is None
    assert mgr.embed_client is None
    assert mgr._initialized is False


@pytest.mark.asyncio
async def test_initialize_builds_both_clients_and_tests_connection(patched_client):
    mgr = _manager()
    await mgr.initialize()
    assert isinstance(mgr.client, patched_client)
    assert isinstance(mgr.embed_client, patched_client)
    assert mgr.client is not mgr.embed_client  # two independent clients
    assert mgr._initialized is True
    mgr.client.list.assert_awaited()  # _test_connection's connectivity check


@pytest.mark.asyncio
async def test_connection_test_failure_does_not_fail_initialize(patched_client):
    mgr = _manager()
    # _test_connection swallows its own exceptions (fail-soft) -- initialize()
    # must still succeed even when the very first list() call fails.
    broken = _FakeAsyncClient(host="x")
    broken.list = AsyncMock(side_effect=ConnectionError("not ready yet"))

    def _client_factory(host):
        return broken

    import shared.ai.ollama_client_base as _base

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_base, "AsyncClient", _client_factory)
        mp.setattr(_mod, "AsyncClient", _client_factory)
        mp.setattr(_base, "OLLAMA_AVAILABLE", True)
        await mgr.initialize()
    assert mgr._initialized is True


@pytest.mark.asyncio
async def test_ensure_model_pulls_when_missing(patched_client):
    mgr = _manager()
    await mgr.initialize()
    mgr.client.list = AsyncMock(return_value={"models": [{"name": "other:latest"}]})
    await mgr.ensure_model("llama3.2")
    mgr.client.pull.assert_awaited_once_with("llama3.2")


@pytest.mark.asyncio
async def test_ensure_model_skips_when_present_with_tag(patched_client):
    mgr = _manager()
    await mgr.initialize()
    mgr.client.list = AsyncMock(return_value={"models": [{"name": "llama3.2:latest"}]})
    await mgr.ensure_model("llama3.2")
    mgr.client.pull.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_model_swallows_errors(patched_client):
    mgr = _manager()
    await mgr.initialize()
    mgr.client.list = AsyncMock(side_effect=RuntimeError("registry down"))
    await mgr.ensure_model("llama3.2")  # must not raise


@pytest.mark.asyncio
async def test_generate_embeddings_lazily_initializes_and_returns_vectors(
    patched_client,
):
    mgr = _manager()
    result = await mgr.generate_embeddings(["hello", "world"], model="nomic-embed")
    assert result == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert mgr._initialized is True


@pytest.mark.asyncio
async def test_generate_embeddings_raises_on_backend_error(patched_client):
    mgr = _manager()
    await mgr.initialize()
    mgr.embed_client.embeddings = AsyncMock(side_effect=RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="embedding generation failed"):
        await mgr.generate_embeddings(["hello"], model="nomic-embed")


@pytest.mark.asyncio
async def test_generate_embeddings_raises_on_empty_vector(patched_client):
    mgr = _manager()
    await mgr.initialize()
    mgr.embed_client.embeddings = AsyncMock(return_value={"embedding": []})
    with pytest.raises(RuntimeError, match="empty vector"):
        await mgr.generate_embeddings(["hello"], model="nomic-embed")


@pytest.mark.asyncio
async def test_generate_response_success(patched_client):
    mgr = _manager()
    result = await mgr.generate_response("what is up", model="command-r")
    assert result["text"] == "hi"
    assert result["tokens_used"] == 8
    assert "error" not in result


@pytest.mark.asyncio
async def test_generate_response_failure_returns_error_dict_not_raise(patched_client):
    mgr = _manager()
    await mgr.initialize()
    mgr.client.generate = AsyncMock(side_effect=RuntimeError("boom"))
    result = await mgr.generate_response("hi", model="command-r")
    assert result["error"] is True
    assert "Error generating response" in result["text"]


@pytest.mark.asyncio
async def test_generate_response_builds_prompt_with_context(patched_client):
    mgr = _manager()
    await mgr.generate_response("what is up", model="command-r", context="ctx info")
    call_kwargs = mgr.client.generate.call_args.kwargs
    assert "ctx info" in call_kwargs["prompt"]
    assert "what is up" in call_kwargs["prompt"]


@pytest.mark.asyncio
async def test_initialize_raises_when_ollama_package_missing(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", False)
    mgr = _manager()
    with pytest.raises(RuntimeError, match="Ollama package not installed"):
        await mgr.generate_response("hi")
