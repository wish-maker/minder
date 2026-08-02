"""Unit tests for the failover-aware 404 message (rag-pipeline/rag/ollama_manager).

#249: a model-not-found 404 through the failover router is ambiguous — it could be
a genuinely nonexistent model, or a model that only lives on the external primary
while the router has quietly fallen back to the internal Ollama. Verifies the
message-rewriting branches without touching a real Ollama/router.
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


_describe_failover_404 = _load_ollama_manager()._describe_failover_404


def _mock_response(upstream_header: str):
    resp = MagicMock()
    resp.headers = {"x-ollama-upstream": upstream_header} if upstream_header else {}
    return resp


class _FakeAsyncClientCtx:
    """Mimics `async with httpx.AsyncClient(...) as client: await client.get(...)`."""

    def __init__(self, response=None, raise_on_init=None):
        self._response = response
        self._raise_on_init = raise_on_init
        if raise_on_init:
            raise raise_on_init

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, *a, **k):
        return self._response


@pytest.mark.asyncio
async def test_backup_upstream_gets_the_clarifying_message():
    ctx = _FakeAsyncClientCtx(response=_mock_response("minder-ollama:11434"))
    with patch("rag_pipeline_ollama_manager.httpx.AsyncClient", return_value=ctx):
        result = await _describe_failover_404("command-r", "model not found")
    assert "internal fallback" in result
    assert "command-r" in result
    assert result.startswith("model not found")


@pytest.mark.asyncio
async def test_primary_upstream_leaves_message_unchanged():
    ctx = _FakeAsyncClientCtx(response=_mock_response("192.168.1.50:11434"))
    with patch("rag_pipeline_ollama_manager.httpx.AsyncClient", return_value=ctx):
        result = await _describe_failover_404("command-r", "model not found")
    assert result == "model not found"


@pytest.mark.asyncio
async def test_no_upstream_header_leaves_message_unchanged():
    # Not actually behind the router (or router omitted the header) — don't guess.
    ctx = _FakeAsyncClientCtx(response=_mock_response(""))
    with patch("rag_pipeline_ollama_manager.httpx.AsyncClient", return_value=ctx):
        result = await _describe_failover_404("command-r", "model not found")
    assert result == "model not found"


@pytest.mark.asyncio
async def test_check_failure_leaves_message_unchanged():
    with patch(
        "rag_pipeline_ollama_manager.httpx.AsyncClient",
        side_effect=RuntimeError("no route"),
    ):
        result = await _describe_failover_404("command-r", "model not found")
    assert result == "model not found"
