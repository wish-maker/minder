"""
Minder RAG Pipeline Service - Production Ready
Real Ollama integration with proper embedding generation and LLM inference
"""

import sys
from contextlib import asynccontextmanager

from core import state
from fastapi import FastAPI
from routes.rag import router as rag_router
from routes.system import router as system_router

from config import settings

# Shared library (needs src/ on the path)
sys.path.insert(0, "/app/src")
from shared.errors import install_global_exception_handler  # noqa: E402
from shared.log import setup_logging  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402

# Standardised on shared.log like the other 7 services (#49). basicConfig configures
# the root logger, so the rag/domain package loggers propagate to it and log
# consistently — no manual per-package handler wiring needed.
logger = setup_logging("rag-pipeline", level=settings.LOG_LEVEL)


# ============================================================================
# FastAPI App
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage/Ollama on startup (see body); no explicit shutdown work."""
    logger.info("🚀 Starting RAG Pipeline service...")
    logger.info(f"Qdrant: {settings.QDRANT_HOST}:{settings.QDRANT_PORT}")
    logger.info(f"Ollama: {settings.OLLAMA_HOST}")
    logger.info(f"Default LLM: {settings.OLLAMA_LLM_MODEL}")
    logger.info(f"Default Embedding: {settings.OLLAMA_EMBEDDING_MODEL}")

    # Load data from PostgreSQL if available
    if state.PG_AVAILABLE:
        try:
            # Initialize database schema (will preserve existing data)
            await state.initialize_schema()

            loaded_kbs = await state.load_kb_from_postgres()
            state.knowledge_bases.update(loaded_kbs)
            logger.info(f"✅ Loaded {len(loaded_kbs)} knowledge bases from PostgreSQL")

            loaded_pipelines = await state.load_pipelines_from_postgres()
            state.rag_pipelines.update(loaded_pipelines)
            logger.info(
                f"✅ Loaded {len(loaded_pipelines)} RAG pipelines from PostgreSQL"
            )

            # Initialize ConversationRepository for conversational RAG
            if state.CONVERSATION_REPO_AVAILABLE and state.pg_client.pg_pool:
                try:
                    state.conversation_repository = state.ConversationRepository(
                        state.pg_client.pg_pool
                    )
                    logger.info("✅ ConversationRepository initialized")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize ConversationRepository: {e}")
                    state.conversation_repository = None
            else:
                logger.warning(
                    "⚠️  ConversationRepository not available (pg_pool or module missing)"
                )
                state.conversation_repository = None
        except Exception as e:
            logger.error(f"❌ Failed to load from PostgreSQL: {e}")
    else:
        logger.info("ℹ️  Using in-memory storage (PostgreSQL not available)")

    # Initialize Ollama manager
    if state.OLLAMA_AVAILABLE:
        try:
            await state.ollama_manager.initialize()
            logger.info("✅ Ollama manager initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama manager: {e}")
            # Don't fail startup, just log the error
    else:
        logger.warning("⚠️  Ollama not available, RAG features will be limited")

    # Report active advanced-RAG methods on this host (see #45; GET /capabilities).
    active = [
        name
        for name, obj in (
            ("hyde", state.hyde_expander),
            ("self_rag", state.self_rag_pipeline),
            ("auto", state.decision_engine),
            ("corrective", state.corrective_pipeline),
            ("rerank", state.reranker),
            ("compress", state.compressor),
        )
        if obj is not None
    ]
    logger.info(f"🧠 RAG methods active: standard, {', '.join(active)}")

    yield


app = FastAPI(
    title="Minder RAG Pipeline",
    description="Production RAG Pipeline with Ollama integration",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)

install_global_exception_handler(
    app, logger, is_development=settings.ENVIRONMENT == "development"
)

app.include_router(system_router)
app.include_router(rag_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
