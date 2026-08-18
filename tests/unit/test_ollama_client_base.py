"""Unit tests for the shared Ollama client init lifecycle (#367).

shared.ai.ollama_client_base.OllamaClientBase is the extraction of what
model-management's and rag-pipeline's independent OllamaManager classes both
duplicated: client/_initialized state, initialize()'s try/except, and the
lazy-init guard. Covered directly here since it has no config/settings
dependency (unlike the two services' own ollama_manager.py modules, which need
their existing import-isolation helpers -- see
test_model_management_ollama_manager.py / test_rag_pipeline_ollama_manager.py).
"""

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

import shared.ai.ollama_client_base as base_mod
from shared.ai.ollama_client_base import OllamaClientBase

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "shared"
    / "ai"
    / "ollama_client_base.py"
)


class _FakeAsyncClient:
    def __init__(self, host):
        self.host = host


def test_init_sets_initial_state():
    mgr = OllamaClientBase(host="http://ollama:11434")
    assert mgr.client is None
    assert mgr._initialized is False
    assert mgr._host == "http://ollama:11434"


def test_initialize_builds_client_and_flags_initialized(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    mgr = OllamaClientBase(host="http://ollama:11434")
    asyncio.run(mgr.initialize())
    assert isinstance(mgr.client, _FakeAsyncClient)
    assert mgr.client.host == "http://ollama:11434"
    assert mgr._initialized is True


def test_initialize_raises_when_ollama_unavailable(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", False)
    mgr = OllamaClientBase(host="http://ollama:11434")
    with pytest.raises(RuntimeError, match="Ollama package not installed"):
        asyncio.run(mgr.initialize())
    assert mgr._initialized is False


def test_initialize_propagates_client_construction_failure(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)

    def _boom(host):
        raise ConnectionError("no route to host")

    monkeypatch.setattr(base_mod, "AsyncClient", _boom)
    mgr = OllamaClientBase(host="http://ollama:11434")
    with pytest.raises(ConnectionError):
        asyncio.run(mgr.initialize())
    assert mgr._initialized is False
    assert mgr.client is None


def test_post_connect_is_a_noop_by_default(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    mgr = OllamaClientBase(host="http://ollama:11434")
    asyncio.run(mgr.initialize())  # would raise if _post_connect had a real body
    assert mgr._initialized is True


def test_subclass_post_connect_hook_runs_before_initialized_flag(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    seen = {}

    class _Sub(OllamaClientBase):
        async def _post_connect(self):
            # _initialized must still be False here -- the hook runs BEFORE it's set.
            seen["initialized_during_hook"] = self._initialized
            seen["client_set_during_hook"] = self.client is not None

    mgr = _Sub(host="http://ollama:11434")
    asyncio.run(mgr.initialize())
    assert seen == {"initialized_during_hook": False, "client_set_during_hook": True}
    assert mgr._initialized is True


def test_subclass_post_connect_failure_propagates_and_leaves_uninitialized(
    monkeypatch,
):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)

    class _Sub(OllamaClientBase):
        async def _post_connect(self):
            raise RuntimeError("second client failed to connect")

    mgr = _Sub(host="http://ollama:11434")
    with pytest.raises(RuntimeError, match="second client failed to connect"):
        asyncio.run(mgr.initialize())
    assert mgr._initialized is False


def test_ensure_initialized_calls_initialize_only_once(monkeypatch):
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    calls = {"n": 0}

    class _Sub(OllamaClientBase):
        async def initialize(self):
            calls["n"] += 1
            await super().initialize()

    mgr = _Sub(host="http://ollama:11434")
    asyncio.run(mgr._ensure_initialized())
    asyncio.run(mgr._ensure_initialized())
    asyncio.run(mgr._ensure_initialized())
    assert calls["n"] == 1


def test_ensure_initialized_noop_when_already_initialized(monkeypatch):
    mgr = OllamaClientBase(host="http://ollama:11434")
    mgr._initialized = True

    async def _boom():
        raise AssertionError("initialize() should not be called")

    monkeypatch.setattr(mgr, "initialize", _boom)
    asyncio.run(mgr._ensure_initialized())  # must not raise


def test_ensure_initialized_serializes_concurrent_callers_after_a_failed_startup_init(
    monkeypatch,
):
    """If Ollama is unreachable at FastAPI-lifespan startup, that failure is only
    logged (never fatal), so _initialized stays False -- the next wave of
    concurrent requests must not each independently race to call initialize()
    and overwrite self.client. Without the lock, both `calls["n"]` would hit 2
    and both concurrent callers would briefly observe a half-built self.client
    from the OTHER caller's in-flight initialize()."""
    monkeypatch.setattr(base_mod, "OLLAMA_AVAILABLE", True)
    monkeypatch.setattr(base_mod, "AsyncClient", _FakeAsyncClient)
    calls = {"n": 0}

    class _Sub(OllamaClientBase):
        async def initialize(self):
            calls["n"] += 1
            # Yield control mid-init so a second concurrent caller's
            # _ensure_initialized() actually overlaps with this one, instead of
            # running to completion before the second call even starts.
            await asyncio.sleep(0)
            await super().initialize()

    mgr = _Sub(host="http://ollama:11434")

    async def _run_concurrently():
        await asyncio.gather(mgr._ensure_initialized(), mgr._ensure_initialized())

    asyncio.run(_run_concurrently())
    assert calls["n"] == 1
    assert mgr._initialized is True


def test_ollama_unavailable_when_package_cannot_be_imported():
    """The module-level `try: from ollama import AsyncClient` guard -- OLLAMA_AVAILABLE
    is real in this environment (the ollama package IS installed), so this loads a
    throwaway independent copy of the module with `ollama` poisoned in sys.modules to
    force the ImportError, rather than touching the real cached
    shared.ai.ollama_client_base module every other test in this file (and
    test_rag_pipeline_ollama_manager.py / test_model_management_ollama_manager.py)
    already imports."""
    saved_ollama = sys.modules.get("ollama")
    sys.modules["ollama"] = None  # `from ollama import X` raises ImportError on None
    try:
        spec = importlib.util.spec_from_file_location(
            "ollama_client_base_import_guard_test", _MODULE_PATH
        )
        fresh = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fresh)
    finally:
        if saved_ollama is not None:
            sys.modules["ollama"] = saved_ollama
        else:
            sys.modules.pop("ollama", None)

    assert fresh.OLLAMA_AVAILABLE is False
    assert fresh.AsyncClient is None
