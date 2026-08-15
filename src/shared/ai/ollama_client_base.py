"""Shared Ollama client init lifecycle (#367).

model-management (`core/ollama_manager.py`) and rag-pipeline (`rag/ollama_manager.py`)
each own an independent `OllamaManager` with near-identical init lifecycles: the same
`client`/`_initialized` shape, the same `initialize()` try/except + log strings, and
the same `if not self._initialized: await self.initialize()` lazy-init guard repeated
before every public method.

This extracts ONLY that lifecycle -- deliberately narrow (#367's own reasoning):
both services are on the model-serving hot path, so a subtly wrong extraction would
surface as a production inference outage, not a test failure. Everything else stays
a subclass concern:
  - model-management wraps failures as `HTTPException` for its own routes;
    rag-pipeline does not. This base raises the bare exception either way and lets
    each subclass decide how to present that to its callers.
  - rag-pipeline needs a second client (`embed_client`) plus a connection test before
    `_initialized` is set True; model-management doesn't. See `_post_connect()`.
"""

import asyncio
import logging
from typing import Optional

# Ollama client — guarded so the module imports even when the package is absent
# (e.g. lint/tests); OLLAMA_AVAILABLE gates real use. Both services previously
# duplicated this exact try/except; centralized here and re-exported by each
# service's own ollama_manager.py so `from core.ollama_manager import OLLAMA_AVAILABLE`
# / `from rag.ollama_manager import OLLAMA_AVAILABLE` keep working unchanged.
try:
    from ollama import AsyncClient

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    AsyncClient = None  # type: ignore[assignment,misc]
    # never called: initialize() raises before touching this when OLLAMA_AVAILABLE
    # is False; bound as None (rather than left unbound) purely so
    # `from ... import AsyncClient` -- used by rag-pipeline's OllamaManager for its
    # own second client -- stays importable.
    logging.warning("ollama package not installed. Install with: pip install ollama")

logger = logging.getLogger("minder.ollama_client_base")


class OllamaClientBase:
    """Owns `client`/`_initialized` and the init lifecycle. Subclasses add their own
    model-management/RAG-specific methods on top, and call `_ensure_initialized()`
    (the lazy-init guard) before using `self.client`.
    """

    def __init__(self, host: str):
        self._host = host
        self.client: Optional["AsyncClient"] = None
        self._initialized = False
        # Guards _ensure_initialized's lazy-init check (#367 follow-up, found in a
        # background audit): if Ollama is unreachable at FastAPI-lifespan startup,
        # that failure is only logged, never fatal (see initialize()'s docstring),
        # so _initialized stays False and the next wave of concurrent requests
        # would otherwise each independently see False and each call initialize()
        # at once -- racing to overwrite self.client (and, for rag-pipeline's
        # subclass, self.embed_client + rerun its own connection test) instead of
        # exactly one of them doing the real work.
        self._init_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Build the Ollama client. Raises on failure -- callers/subclasses decide
        how to present that (see module docstring)."""
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama package not installed")
        try:
            self.client = AsyncClient(host=self._host)
            await self._post_connect()
            self._initialized = True
            logger.info(f"✅ Ollama client initialized: {self._host}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama client: {e}")
            raise

    async def _post_connect(self) -> None:
        """Hook for subclass setup that must happen after `self.client` connects but
        before `_initialized` is set True (e.g. rag-pipeline's second client + its own
        connection test). No-op by default. Runs inside `initialize()`'s try block, so
        anything here that shouldn't be able to fail `initialize()` must catch its own
        exceptions -- exactly as rag-pipeline's existing `_test_connection` already
        does.
        """
        return None

    async def _ensure_initialized(self) -> None:
        """The lazy-init guard previously repeated before every public method on
        both services' managers. Double-checked locking: the fast path (already
        initialized) takes no lock at all; only the first concurrent wave after a
        failed startup init contends for it, and only one of them actually calls
        initialize() -- the rest see _initialized True once they acquire the lock
        and return immediately.
        """
        if self._initialized:
            return
        async with self._init_lock:
            if not self._initialized:
                await self.initialize()
