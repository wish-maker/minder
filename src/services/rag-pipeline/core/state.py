"""Shared runtime state and wiring for the RAG Pipeline service.

Holds the in-memory stores, the Ollama manager, the optional advanced-RAG
components, PostgreSQL persistence helpers, the Qdrant client factory, and the
Prometheus collectors. main.py's lifespan populates these on startup; the route
modules import them here.

`conversation_repository` is reassigned at runtime, so consumers must reach it
via ``await state.ensure_conversation_repository()`` (which also lazily rebuilds
it if the PG pool wasn't ready at startup) rather than importing the name
directly — a direct import would bind the initial ``None``.
"""

import logging
from typing import Any, Dict, Optional

from prometheus_client import Counter, Histogram
from qdrant_client import QdrantClient
from rag.ollama_manager import OLLAMA_AVAILABLE, OllamaManager  # noqa: F401

from config import settings

logger = logging.getLogger("minder.rag-pipeline")

# ============================================================================
# Prometheus Metrics (domain-specific; HTTP request metrics come from
# shared.metrics.setup_metrics, wired in main)
# ============================================================================

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

# Import PostgreSQL client functions. pg_client lives in the repositories/ package
# (persistence layer); the name `pg_client` is bound here so main.py can reach
# state.pg_client.pg_pool. Falls back to in-memory storage if the module is absent.
try:
    from repositories import pg_client

    save_kb_to_postgres = pg_client.save_kb_to_postgres
    load_kb_from_postgres = pg_client.load_kb_from_postgres
    delete_kb_from_postgres = pg_client.delete_kb_from_postgres
    save_pipeline_to_postgres = pg_client.save_pipeline_to_postgres
    load_pipelines_from_postgres = pg_client.load_pipelines_from_postgres
    delete_pipeline_from_postgres = pg_client.delete_pipeline_from_postgres
    initialize_schema = pg_client.initialize_schema
    PG_AVAILABLE = True
    logger.info("✅ PostgreSQL persistence available")
except ImportError:
    PG_AVAILABLE = False
    logger.warning("⚠️  pg_client not available, using in-memory storage")

# Conversation Repository for conversational RAG
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

# Reassigned in lifespan — read via ensure_conversation_repository(), never imported by name.
conversation_repository: Optional["ConversationRepository"] = None


async def ensure_conversation_repository():
    """Return the conversation repository, lazily (re)building it if it was not
    wired at startup.

    ``conversation_repository`` is set once during lifespan startup, but the PG
    pool it needs can legitimately be unavailable at that exact moment: Postgres
    is still finishing crash-recovery ("the database system is starting up")
    when rag-pipeline boots, even behind ``depends_on: service_healthy``
    (``pg_isready`` reports ready during a transient first-boot window). Before
    this, that single failed attempt left conversation history AND conversational
    memory permanently 503 for the whole container lifetime, while every other
    PG-backed feature recovered lazily via ``pg_client.get_pg_connection()``.
    Mirror that recovery here — build the repo on first use against the
    now-available pool. Returns None only when conversational storage is
    genuinely unavailable (module missing, or PG still unreachable)."""
    global conversation_repository
    if conversation_repository is not None:
        return conversation_repository
    if not (CONVERSATION_REPO_AVAILABLE and PG_AVAILABLE):
        return None
    try:
        pool = await pg_client.get_pg_connection()
    except Exception as e:  # pool still not creatable (PG down) — stay degraded
        logger.warning(f"⚠️  Conversation repository unavailable (pg pool): {e}")
        return None
    if pool is None:
        return None
    conversation_repository = ConversationRepository(pool)
    logger.info("✅ ConversationRepository initialized (lazy)")
    return conversation_repository


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
    from domain.decision_engine import AgentDecisionEngine

    _ollama_host = (
        settings.OLLAMA_HOST.replace("http://", "").replace("https://", "").rstrip("/")
        or "minder-ollama:11434"
    )
    decision_engine = AgentDecisionEngine(ollama_host=_ollama_host)
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ Decision engine unavailable: {e}")

# Corrective RAG (LLM-graded, no heavy deps), plus the capability-adaptive reranker
# and contextual compressor. All instantiate cheaply (the cross-encoder loads its
# torch model lazily and self-degrades to an LLM re-rank when sentence-transformers
# is absent — e.g. on the Pi). See #45.
corrective_pipeline = None
reranker = None
compressor = None
try:
    from domain.pipelines.corrective_rag import CorrectiveRAGPipeline

    corrective_pipeline = CorrectiveRAGPipeline()
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ Corrective RAG unavailable: {e}")
try:
    from domain.rerankers.cross_encoder import CrossEncoderReranker

    reranker = CrossEncoderReranker()
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ Reranker unavailable: {e}")
try:
    from domain.compressors.contextual import ContextualCompressor

    compressor = ContextualCompressor()
except Exception as e:  # pragma: no cover
    logger.warning(f"⚠️ Compressor unavailable: {e}")

# Query orchestration lives in the rag/ package (per-method strategy modules + runner).
from rag.runner import GenerationError, RagComponents, run_query  # noqa: E402,F401

# ============================================================================
# Qdrant Client Management
# ============================================================================


_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Return the shared Qdrant client, created once.

    Cached so we don't open (and abandon) a fresh connection pool on every call —
    the old per-request construction leaked a client each time. The client is
    synchronous; migrating the hot paths off the event loop is tracked separately
    (#211).
    """
    global _qdrant_client
    if _qdrant_client is None:
        _qdrant_client = QdrantClient(
            url=f"http://{settings.QDRANT_HOST}:{settings.QDRANT_PORT}"
        )
    return _qdrant_client
