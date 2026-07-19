"""Ollama client management for the RAG pipeline (embeddings + LLM generation).

Extracted from main.py. The service injects a single OllamaManager instance into
the query runner / RAG method modules, which receive it as an opaque
`llm_manager`; only main.py constructs it.
"""

import logging
from typing import Any, Dict, List, Optional

from config import DEFAULT_EMBEDDING_MODEL, DEFAULT_LLM_MODEL, OLLAMA_HOST

logger = logging.getLogger(__name__)

# Ollama client for real embeddings and LLM
try:
    from ollama import AsyncClient

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("ollama package not installed. Install with: pip install ollama")


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
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Generate response using Ollama LLM"""
        if not self._initialized:
            await self.initialize()

        await self.ensure_model(model)

        # Build full prompt with context
        full_prompt = self._build_rag_prompt(prompt, context)

        try:
            response = await self.client.generate(
                model=model,
                prompt=full_prompt,
                stream=stream,
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
            return {
                "text": f"Error generating response: {str(e)}",
                "model": model,
                "context": context,
                "tokens_used": 0,
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
