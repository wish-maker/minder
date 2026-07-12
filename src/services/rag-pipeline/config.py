"""Configuration constants for the RAG Pipeline service.

Centralizes the environment-driven settings that were previously defined inline
in main.py so the service module, the Ollama manager, and the Pydantic models
share a single source of truth.
"""

import os

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
MODEL_MANAGEMENT_URL = os.getenv(
    "MODEL_MANAGEMENT_URL", "http://minder-model-management:8005"
)

# Default models (can be overridden per knowledge base)
DEFAULT_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
DEFAULT_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")

# Embedding dimensions (depends on model)
EMBEDDING_DIMENSIONS = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
}
