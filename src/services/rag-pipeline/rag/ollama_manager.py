"""Ollama client management for the RAG pipeline (embeddings + LLM generation).

Extracted from main.py. The service injects a single OllamaManager instance into
the query runner / RAG method modules, which receive it as an opaque
`llm_manager`; only main.py constructs it.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings
from shared.ai.ollama_client_base import (  # noqa: F401 -- OLLAMA_AVAILABLE re-exported for state.py
    OLLAMA_AVAILABLE,
    AsyncClient,
    OllamaClientBase,
)

logger = logging.getLogger(__name__)


def _model_name(entry: Dict[str, Any]) -> str:
    """Name of a model as returned by ``client.list()``.

    ollama>=0.5 renamed the list-entry field ``name``→``model`` (model-management's
    models_api.py made the same accommodation). Reading only ``entry["name"]`` on a
    newer client raises ``KeyError``, which ``ensure_model`` swallows — so it silently
    stops pulling missing models. Accept either key.
    """
    return entry.get("model") or entry.get("name") or ""


# ResponseError is rag-pipeline-specific (used by _describe_failover_404 below, not
# part of the shared init lifecycle) -- OLLAMA_AVAILABLE above already covers whether
# the real `ollama` package is installed.
try:
    from ollama import ResponseError
except ImportError:
    ResponseError = Exception  # type: ignore[misc,assignment]  # unreachable without the package


async def _describe_failover_404(model: str, base_error: str) -> str:
    """#249: a model-not-found 404 is ambiguous in failover mode — it could mean the
    model genuinely doesn't exist anywhere, or that it only lives on the external
    primary while the router has quietly fallen back to the internal Ollama. Probe
    the primary directly (mirrors scripts/setup/status.py's `_primary_reachable`,
    just from inside the container instead of via `docker exec`) and say which case
    this is instead of surfacing a bare, misleading 404. Best-effort: any hiccup
    probing it just returns the original message unchanged.

    Earlier approach tried inferring this from the router's X-Ollama-Upstream
    response header instead of probing the primary directly, and was wrong: nginx's
    upstream circuit breaker (`max_fails=1 fail_timeout=10s`) skips a recently-failed
    primary entirely on subsequent requests, so the header only shows BOTH attempts
    (primary then backup, comma-separated) for the first request after each
    fail_timeout window — every request after that shows just the backup's address
    with no comma, indistinguishable from "the primary answered directly".
    Confirmed live (2026-08-02): identical requests a few seconds apart flipped
    between a 2-entry and a 1-entry header with no change in which backend was
    actually serving. A direct reachability probe has no such timing dependency.
    """
    if not settings.OLLAMA_FAILOVER_PRIMARY:
        return base_error  # not configured for failover on this container
    primary_url = settings.OLLAMA_FAILOVER_PRIMARY
    if not primary_url.startswith("http"):
        primary_url = f"http://{primary_url}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{primary_url}/api/tags")
        primary_reachable = resp.status_code < 500
    except Exception:
        primary_reachable = False
    if primary_reachable:
        return (
            base_error  # primary answered — the model genuinely doesn't exist anywhere
        )
    return (
        f"{base_error} — the external primary ({settings.OLLAMA_FAILOVER_PRIMARY}) is "
        "currently unreachable, so this was served by the internal fallback. "
        f"Model '{model}' may only exist on the primary; it should work again once "
        "the primary recovers (see `bash setup.sh status` for the active backend)."
    )


class OllamaManager(OllamaClientBase):
    """Manage Ollama client connections"""

    def __init__(self):
        super().__init__(host=settings.OLLAMA_HOST)
        self.embed_client: Optional["AsyncClient"] = None

    async def _post_connect(self) -> None:
        """Second client + connection test -- runs after `self.client` connects but
        before `_initialized` is set True (see OllamaClientBase._post_connect)."""
        self.embed_client = AsyncClient(host=self._host)
        await self._test_connection()

    async def _test_connection(self):
        """Test Ollama connection"""
        try:
            # List available models to verify connection
            models = await self.client.list()
            logger.info(
                f"✅ Ollama connection verified. Available models: {[_model_name(m) for m in models.get('models', [])]}"
            )
        except Exception as e:
            logger.warning(f"⚠️  Ollama connection test failed: {e}")
            # Don't fail - models might not be pulled yet

    async def ensure_model(self, model_name: str):
        """Ensure model is available, pull if necessary"""
        try:
            assert self.client is not None
            models = await self.client.list()
            available = [_model_name(m) for m in models.get("models", [])]
            available = [name for name in available if name]

            # Check if model exists with any version tag
            model_exists = any(
                model_name in available_model
                or available_model.startswith(model_name + ":")
                for available_model in available
            )

            if not model_exists:
                logger.info(f"📥 Pulling model: {model_name}")
                assert self.client is not None
                await self.client.pull(model_name)
                logger.info(f"✅ Model pulled: {model_name}")
            else:
                logger.debug(f"✅ Model {model_name} already available")

        except Exception as e:
            logger.warning(f"⚠️  Could not verify/pull model {model_name}: {e}")

    # Ollama's /api/embed accepts a batch `input` list and returns embeddings in
    # order, so a document's chunks embed in a handful of round-trips instead of one
    # HTTP call per chunk (the dominant ingest cost on the Pi). Capped so a very large
    # document doesn't build one enormous request/response.
    EMBED_BATCH_SIZE = 96

    async def generate_embeddings(
        self, texts: List[str], model: str = settings.OLLAMA_EMBEDDING_MODEL
    ) -> List[List[float]]:
        """Generate embeddings using Ollama (batched)."""
        await self._ensure_initialized()

        await self.ensure_model(model)

        if not texts:
            return []

        assert self.embed_client is not None
        embeddings: List[List[float]] = []
        for start in range(0, len(texts), self.EMBED_BATCH_SIZE):
            batch = texts[start : start + self.EMBED_BATCH_SIZE]
            try:
                response = await self.embed_client.embed(model=model, input=batch)
                vectors = response.get("embeddings", []) or []
            except Exception as e:
                # Do NOT substitute a zero-vector — that silently corrupts the index
                # (upload would "succeed" with an unsearchable doc, queries return
                # garbage). Fail loudly so callers can surface a real error. See #77.
                logger.error(f"❌ Embedding generation failed ({model}): {e}")
                raise RuntimeError(
                    f"embedding generation failed for model '{model}': {e}"
                ) from e
            # A short/over-long batch would silently misalign chunks with their
            # vectors on upsert — treat any count mismatch as a hard failure.
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"embedding backend returned {len(vectors)} vectors for "
                    f"{len(batch)} inputs (model '{model}')"
                )
            for vector in vectors:
                if not vector:
                    raise RuntimeError(
                        f"embedding backend returned an empty vector for model '{model}'"
                    )
            embeddings.extend(vectors)

        return embeddings

    async def generate_response(
        self,
        prompt: str,
        model: str = settings.OLLAMA_LLM_MODEL,
        context: str = "",
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Generate response using Ollama LLM"""
        await self._ensure_initialized()

        await self.ensure_model(model)

        # Build full prompt with context
        full_prompt = self._build_rag_prompt(prompt, context)

        try:
            assert self.client is not None
            response = await self.client.generate(
                model=model,
                prompt=full_prompt,
                stream=False,
                options={
                    "temperature": temperature,
                    "num_predict": 2000,  # Max tokens
                },
            )

            return {
                "text": response.get("response", ""),
                "model": model,
                "context": context,
                "tokens_used": response.get("prompt_eval_count", 0)
                + response.get("eval_count", 0),
            }

        except Exception as e:
            logger.error(f"❌ LLM generation failed: {e}")
            error_text = str(e)
            # #249: a 404 through the failover router is ambiguous — clarify it when
            # it actually is the "only on the unreachable primary" case. (Cheap
            # early-exit here; _describe_failover_404 also self-guards on
            # OLLAMA_FAILOVER_PRIMARY being set.)
            if (
                isinstance(e, ResponseError)
                and e.status_code == 404
                and settings.OLLAMA_FAILOVER_PRIMARY
            ):
                error_text = await _describe_failover_404(model, error_text)
            # Flag the failure so the query path can surface a real 503 instead of
            # returning this error string as a 200 "answer" (#232). Internal callers
            # (hyde/rerank/corrective/self_rag) ignore the flag and keep degrading.
            return {
                "text": f"Error generating response: {error_text}",
                "model": model,
                "context": context,
                "tokens_used": 0,
                "error": True,
            }

    def _build_rag_prompt(self, question: str, context: str) -> str:
        """Build RAG prompt with context"""
        if context:
            return f"""Context information is below.
---------------------
{context}
---------------------

Given the context information and not prior knowledge, answer the query.
Query: {question}

Answer:"""
        else:
            return f"Answer the following question: {question}"
