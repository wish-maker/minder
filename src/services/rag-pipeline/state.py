"""Shared runtime state and wiring for the RAG Pipeline service.

Holds the in-memory stores, the Ollama manager, the optional advanced-RAG
components, PostgreSQL persistence helpers, the Qdrant client factory, and the
Prometheus collectors. main.py's lifespan populates these on startup; the route
modules import them here.

`conversation_repository` is reassigned at runtime (in lifespan), so consumers
must read it as ``state.conversation_repository`` — importing the name directly
would bind the initial ``None``.
"""

import logging
from typing import Any, Dict, Optional

from prometheus_client import Counter, Gauge, Histogram
from qdrant_client import QdrantClient
from rag.ollama_manager import OLLAMA_AVAILABLE, OllamaManager  # noqa: F401

from config import OLLAMA_HOST, QDRANT_HOST, QDRANT_PORT

logger = logging.getLogger("minder.rag-pipeline")

# ============================================================================
# Prometheus Metrics
# ============================================================================

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

knowledge_bases_total = Gauge(
    "knowledge_bases_total", "Total number of knowledge bases"
)

documents_processed_total = Counter(
    "documents_processed_total", "Total documents processed", ["status"]
)

embedding_generation_duration = Histogram(
    "embedding_generation_duration_seconds", "Time to generate embeddings", ["model"]
)

llm_generation_duration = Histogram(
    "llm_generation_duration_seconds", "Time to generate LLM response", ["model"]
)

# ============================================================================
# PostgreSQL Persistence (Production Storage)
# ============================================================================

# Import PostgreSQL client functions
try:
    from . import pg_client

    save_kb_to_postgres = pg_client.save_kb_to_postgres
    load_kb_from_postgres = pg_client.load_kb_from_postgres
    save_pipeline_to_postgres = pg_client.save_pipeline_to_postgres
    load_pipelines_from_postgres = pg_client.load_pipelines_from_postgres
    initialize_schema = pg_client.initialize_schema
    PG_AVAILABLE = True
    logger.info("✅ PostgreSQL persistence available")
except ImportError:
    try:
        import pg_client

        save_kb_to_postgres = pg_client.save_kb_to_postgres
        load_kb_from_postgres = pg_client.load_kb_from_postgres
        save_pipeline_to_postgres = pg_client.save_pipeline_to_postgres
        load_pipelines_from_postgres = pg_client.load_pipelines_from_postgres
        initialize_schema = pg_client.initialize_schema
        PG_AVAILABLE = True
        logger.info("✅ PostgreSQL persistence available")
    except ImportError:
        PG_AVAILABLE = False
        logger.warning("⚠️  pg_client not available, using in-memory storage")

# Conversation Repository for conversational RAG
try:
    from .repositories.conversation_repository import ConversationRepository

    CONVERSATION_REPO_AVAILABLE = True
except ImportError:
    try:
        from repositories.conversation_repository import ConversationRepository

        CONVERSATION_REPO_AVAILABLE = True
    except ImportError:
        CONVERSATION_REPO_AVAILABLE = False
        logger.warning("⚠️  ConversationRepository not available")

# ============================================================================
# In-memory stores
# ============================================================================

knowledge_bases: Dict[str, Dict[str, Any]] = {}
rag_pipelines: Dict[str, Dict[str, Any]] = {}

# Reassigned in lifespan — read as state.conversation_repository, never imported by name.
conversation_repository: Optional["ConversationRepository"] = None

# ============================================================================
# Ollama manager (OllamaManager lives in rag/ollama_manager.py)
# ============================================================================

ollama_manager = OllamaManager()

# ============================================================================
# Advanced RAG methods (HyDE, Self-RAG, decision engine) — see #45
# Imported defensively: if a module is missing the service still runs Standard
# and Conversational RAG. `ollama_manager` is used directly as the llm_manager
# (its generate_response / generate_embeddings signatures match what they expect).
# ============================================================================
hyde_expander = None
self_rag_pipeline = None
decision_engine = None
try:
    from domain.expansion.hyde import HyDEQueryExpander

    hyde_expander = HyDEQueryExpander()
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ HyDE unavailable: {e}")
try:
    from domain.pipelines.self_rag import SelfRAGPipeline

    self_rag_pipeline = SelfRAGPipeline()
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ Self-RAG unavailable: {e}")
try:
    from agent.decision_engine import AgentDecisionEngine

    _ollama_host = (
        OLLAMA_HOST.replace("http://", "").replace("https://", "").rstrip("/")
        or "minder-ollama:11434"
    )
    decision_engine = AgentDecisionEngine(ollama_host=_ollama_host)
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ Decision engine unavailable: {e}")

# Query orchestration lives in the rag/ package (per-method strategy modules + runner).
from rag.runner import RagComponents, run_query  # noqa: E402,F401

# ============================================================================
# Qdrant Client Management
# ============================================================================


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client"""
    return QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")
