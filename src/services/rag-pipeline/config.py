"""Settings for the RAG Pipeline service.

Centralizes the environment-driven settings that were previously defined inline
in main.py so the service module, the Ollama manager, and the Pydantic models
share a single source of truth.
"""

import sys

# MinderBaseSettings + shared packages live under /app/src (#267).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.config import MinderBaseSettings  # noqa: E402


class Settings(MinderBaseSettings):
    """RAG Pipeline Settings"""

    APP_VERSION: str = "1.0.0"

    # Database
    DB_NAME: str = "minder"

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333

    # Set only in failover mode (ollama-mode failover <url>) — host:port of the
    # external primary the ollama-router prefers. Empty otherwise. See
    # rag/ollama_manager.py's _describe_failover_404 (#249).
    OLLAMA_FAILOVER_PRIMARY: str = ""

    MODEL_MANAGEMENT_URL: str = "http://minder-model-management:8005"

    # Default models (can be overridden per knowledge base)
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_LLM_MODEL: str = "llama3.2"


settings = Settings()

# Embedding dimensions (depends on model) — static data, not env-driven.
EMBEDDING_DIMENSIONS = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
}
