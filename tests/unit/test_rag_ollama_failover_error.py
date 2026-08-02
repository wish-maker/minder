"""Unit tests for the failover-aware 404 message (rag-pipeline/rag/ollama_manager).

#249: a model-not-found 404 through the failover router is ambiguous — it could be
a genuinely nonexistent model, or a model that only lives on the external primary
while the router has quietly fallen back to the internal Ollama. Verifies the
message-rewriting branches by mocking a direct probe of the primary, without
touching a real Ollama/router.

An earlier version of this tested inferring the active backend from the router's
X-Ollama-Upstream response header instead. That was wrong (caught live on hantal,
2026-08-02): nginx's upstream circuit breaker skips a recently-failed primary
entirely on subsequent requests, so the header's shape depends on request timing
relative to nginx's fail_timeout window, not on which backend is actually active.
Probing the primary directly has no such timing dependency.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "rag-pipeline"


def _load_ollama_manager():
    # ollama_manager.py does a bare `from config import ...`; several sibling
    # services also ship a bare config.py, and whichever one the shared root
    # conftest.py happened to import first wins the "config" name in sys.modules.
    # Force-load THIS service's config.py under that name first so the module
    # under test gets the right one, regardless of test run order.
    config_spec = importlib.util.spec_from_file_location(
        "config", _SERVICE_DIR / "config.py"
    )
    config_mod = importlib.util.module_from_spec(config_spec)
    sys.modules["config"] = config_mod
    config_spec.loader.exec_module(config_mod)

    spec = importlib.util.spec_from_file_location(
        "rag_pipeline_ollama_manager", _SERVICE_DIR / "rag" / "ollama_manager.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[
        "rag_pipeline_ollama_manager"
    ] = mod  # so unittest.mock.patch(...) can find it
    spec.loader.exec_module(mod)
    return mod


_mod = _load_ollama_manager()
_describe_failover_404 = _mod._describe_failover_404


class _FakeAsyncClientCtx:
    """Mimics `async with httpx.AsyncClient(...) as client: await client.get(...)`."""

    def __init__(self, response=None, raise_on_get=None):
        self._response = response
        self._raise_on_get = raise_on_get

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        if self._raise_on_get:
            raise self._raise_on_get
        return self._response


def _mock_response(status_code: int):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


@pytest.mark.asyncio
async def test_no_failover_primary_configured_leaves_message_unchanged():
    # Not in failover mode at all (the default) — never even probes.
    with patch("rag_pipeline_ollama_manager.OLLAMA_FAILOVER_PRIMARY", ""), patch(
        "rag_pipeline_ollama_manager.httpx.AsyncClient"
    ) as client_cls:
        result = await _describe_failover_404("command-r", "model not found")
    assert result == "model not found"
    client_cls.assert_not_called()


@pytest.mark.asyncio
async def test_primary_reachable_leaves_message_unchanged():
    ctx = _FakeAsyncClientCtx(response=_mock_response(200))
    with patch(
        "rag_pipeline_ollama_manager.OLLAMA_FAILOVER_PRIMARY", "192.168.1.50:11434"
    ), patch("rag_pipeline_ollama_manager.httpx.AsyncClient", return_value=ctx):
        result = await _describe_failover_404("command-r", "model not found")
    # Primary answered directly — the model genuinely doesn't exist anywhere.
    assert result == "model not found"


@pytest.mark.asyncio
async def test_primary_unreachable_gets_clarifying_message():
    ctx = _FakeAsyncClientCtx(raise_on_get=ConnectionError("no route to host"))
    with patch(
        "rag_pipeline_ollama_manager.OLLAMA_FAILOVER_PRIMARY", "10.255.255.1:11434"
    ), patch("rag_pipeline_ollama_manager.httpx.AsyncClient", return_value=ctx):
        result = await _describe_failover_404("command-r", "model not found")
    assert result.startswith("model not found")
    assert "internal fallback" in result
    assert "10.255.255.1:11434" in result
    assert "command-r" in result


@pytest.mark.asyncio
async def test_primary_5xx_counts_as_unreachable():
    ctx = _FakeAsyncClientCtx(response=_mock_response(503))
    with patch(
        "rag_pipeline_ollama_manager.OLLAMA_FAILOVER_PRIMARY", "10.255.255.1:11434"
    ), patch("rag_pipeline_ollama_manager.httpx.AsyncClient", return_value=ctx):
        result = await _describe_failover_404("command-r", "model not found")
    assert "internal fallback" in result
