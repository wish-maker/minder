"""Ollama client management for the RAG pipeline (embeddings + LLM generation).

Extracted from main.py. The service injects a single OllamaManager instance into
the query runner / RAG method modules, which receive it as an opaque
`llm_manager`; only main.py constructs it.
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    OLLAMA_FAILOVER_PRIMARY,
    OLLAMA_HOST,
)

logger = logging.getLogger(__name__)

# Ollama client for real embeddings and LLM
try:
    from ollama import AsyncClient, ResponseError

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    ResponseError = Exception  # type: ignore[misc,assignment]  # unreachable without the package
    logging.warning("ollama package not installed. Install with: pip install ollama")


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
    if not OLLAMA_FAILOVER_PRIMARY:
        return base_error  # not configured for failover on this container
    primary_url = OLLAMA_FAILOVER_PRIMARY
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
        f"{base_error} — the external primary ({OLLAMA_FAILOVER_PRIMARY}) is "
        "currently unreachable, so this was served by the internal fallback. "
        f"Model '{model}' may only exist on the primary; it should work again once "
        "the primary recovers (see `bash setup.sh status` for the active backend)."
    )


class OllamaManager:
    """Manage Ollama client connections"""

    def __init__(self):
        self.client: Optional["AsyncClient"] = None
        self.embed_client: Optional["AsyncClient"] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Ollama clients"""
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama package not installed")

        try:
            self.client = AsyncClient(host=OLLAMA_HOST)
            self.embed_client = AsyncClient(host=OLLAMA_HOST)

            # Test connection
            await self._test_connection()
            self._initialized = True
            logger.info(f"✅ Ollama client initialized: {OLLAMA_HOST}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama client: {e}")
            raise

    async def _test_connection(self):
        """Test Ollama connection"""
        try:
            # List available models to verify connection
            models = await self.client.list()
            logger.info(
                f"✅ Ollama connection verified. Available models: {[m['name'] for m in models.get('models', [])]}"
            )
        except Exception as e:
            logger.warning(f"⚠️  Ollama connection test failed: {e}")
            # Don't fail - models might not be pulled yet

    async def ensure_model(self, model_name: str):
        """Ensure model is available, pull if necessary"""
        try:
            assert self.client is not None
            models = await self.client.list()
            available = [m["name"] for m in models.get("models", [])]

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

    async def generate_embeddings(
        self, texts: List[str], model: str = DEFAULT_EMBEDDING_MODEL
    ) -> List[List[float]]:
        """Generate embeddings using Ollama"""
        if not self._initialized:
            await self.initialize()

        await self.ensure_model(model)

        embeddings = []
        for text in texts:
            try:
                assert self.embed_client is not None
                response = await self.embed_client.embeddings(model=model, prompt=text)
                embedding = response.get("embedding", [])
            except Exception as e:
                # Do NOT substitute a zero-vector — that silently corrupts the index
                # (upload would "succeed" with an unsearchable doc, queries return
                # garbage). Fail loudly so callers can surface a real error. See #77.
                logger.error(f"❌ Embedding generation failed ({model}): {e}")
                raise RuntimeError(
                    f"embedding generation failed for model '{model}': {e}"
                ) from e
            if not embedding:
                raise RuntimeError(
                    f"embedding backend returned an empty vector for model '{model}'"
                )
            embeddings.append(embedding)

        return embeddings

    async def generate_response(
        self,
        prompt: str,
        model: str = DEFAULT_LLM_MODEL,
        context: str = "",
        temperature: float = 0.7,
    ) -> Dict[str, Any]:
        """Generate response using Ollama LLM"""
        if not self._initialized:
            await self.initialize()

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
                and OLLAMA_FAILOVER_PRIMARY
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
