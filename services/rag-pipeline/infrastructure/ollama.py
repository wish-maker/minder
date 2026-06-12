"""
Ollama Client Manager

Manages connections to Ollama LLM service for embedding generation
and text completion. Handles model pulling and connection testing.

This is an infrastructure component with external service dependencies.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Optional dependency handling
try:
    from ollama import AsyncClient
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    AsyncClient = None
    logging.warning("Ollama not available. Install with: pip install ollama")


class OllamaManager:
    """
    Manage Ollama client connections

    Handles connection management, model availability, and provides
    interfaces for embedding generation and text completion.

    Features:
    - Async client management
    - Model pulling and verification
    - Embedding generation with cache support
    - RAG-aware prompt building
    - Connection testing on initialization

    Attributes:
        client (AsyncClient): Client for general operations
        embed_client (AsyncClient): Client for embedding operations
        _initialized (bool): Whether manager is initialized

    Example:
        >>> manager = OllamaManager()
        >>> await manager.initialize()
        >>> embeddings = await manager.generate_embeddings(
        ...     texts=["What is RAG?"],
        ...     model="nomic-embed-text"
        ... )
    """

    def __init__(self, host: str = "localhost:11434"):
        """
        Initialize Ollama manager

        Args:
            host: Ollama server host:port

        Raises:
            ValueError: If host invalid
        """
        if not host:
            raise ValueError("host cannot be empty")

        self.host = host
        self.client: Optional["AsyncClient"] = None
        self.embed_client: Optional["AsyncClient"] = None
        self._initialized = False

        logger.info(f"✅ OllamaManager created: host={host}")

    async def initialize(self) -> None:
        """
        Initialize Ollama clients

        Establishes connection to Ollama server and tests connectivity.

        Raises:
            RuntimeError: If Ollama package not available
            ConnectionError: If connection fails
        """
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama package not installed")

        if self._initialized:
            logger.debug("OllamaManager already initialized")
            return

        try:
            self.client = AsyncClient(host=self.host)
            self.embed_client = AsyncClient(host=self.host)

            # Test connection
            await self._test_connection()

            self._initialized = True
            logger.info(f"✅ Ollama client initialized: {self.host}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama client: {e}")
            raise

    async def _test_connection(self) -> None:
        """
        Test Ollama connection

        Lists available models to verify connectivity.

        Note:
            Logs warning but doesn't fail - models might not be pulled yet
        """
        try:
            models = await self.client.list()
            model_names = [m['name'] for m in models.get('models', [])]
            logger.info(f"✅ Ollama connection verified. Available models: {model_names}")
        except Exception as e:
            logger.warning(f"⚠️ Ollama connection test failed: {e}")

    async def ensure_model(self, model_name: str) -> None:
        """
        Ensure model is available, pull if necessary

        Args:
            model_name: Model name to check/pull

        Raises:
            ValueError: If model_name empty
        """
        if not model_name:
            raise ValueError("model_name cannot be empty")

        try:
            models = await self.client.list()
            available = [m["name"] for m in models.get("models", [])]

            # Check if model exists with any version tag
            model_exists = any(
                model_name in available_model or available_model.startswith(model_name + ":")
                for available_model in available
            )

            if not model_exists:
                logger.info(f"📥 Pulling model: {model_name}")
                await self.client.pull(model_name)
                logger.info(f"✅ Model pulled: {model_name}")
            else:
                logger.debug(f"✅ Model {model_name} already available")

        except Exception as e:
            logger.warning(f"⚠️ Could not verify/pull model {model_name}: {e}")

    async def generate_embeddings(
        self,
        texts: List[str],
        model: str,
        cache: Optional[Any] = None,
        embedding_dimensions: int = 768
    ) -> List[List[float]]:
        """
        Generate embeddings using Ollama with optional cache

        Args:
            texts: List of texts to embed
            model: Embedding model name
            cache: Optional embedding cache instance
            embedding_dimensions: Fallback embedding dimension

        Returns:
            List of embedding vectors

        Raises:
            ValueError: If texts empty or model invalid
        """
        if not texts:
            raise ValueError("texts cannot be empty")

        if not model:
            raise ValueError("model cannot be empty")

        if not self._initialized:
            await self.initialize()

        await self.ensure_model(model)

        embeddings = []

        for text in texts:
            # Check cache first
            if cache is not None:
                cached = cache.get(text)
                if cached is not None:
                    embeddings.append(cached)
                    continue

            # Generate new embedding
            try:
                response = await self.embed_client.embeddings(model=model, prompt=text)
                embedding = response.get("embedding", [])
                embeddings.append(embedding)

                # Cache the result
                if cache is not None:
                    cache.set(text, embedding)

            except Exception as e:
                logger.error(f"❌ Embedding generation failed: {e}")
                # Return zero vector as fallback
                embeddings.append([0.0] * embedding_dimensions)

        return embeddings

    async def generate_response(
        self,
        prompt: str,
        model: str,
        context: str = "",
        temperature: float = 0.7,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Generate response using Ollama LLM

        Args:
            prompt: User prompt/question
            model: LLM model name
            context: Optional context for RAG
            temperature: Sampling temperature (0.0-1.0)
            stream: Whether to stream response

        Returns:
            Dict with keys:
                text (str): Generated response
                model (str): Model used
                context (str): Context provided
                tokens_used (int): Total tokens consumed

        Raises:
            ValueError: If prompt or model invalid
        """
        if not prompt:
            raise ValueError("prompt cannot be empty")

        if not model:
            raise ValueError("model cannot be empty")

        if not 0 <= temperature <= 1:
            raise ValueError(f"temperature must be in [0, 1], got {temperature}")

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
                "tokens_used": response.get("prompt_eval_count", 0) + response.get("eval_count", 0),
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
        """
        Build RAG prompt with context

        Args:
            question: User question
            context: Retrieved context

        Returns:
            Formatted prompt string
        """
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
