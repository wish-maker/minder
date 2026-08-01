"""System & observability routes: /health, /metrics, /initialize, / (root)."""

import asyncio
import os
from datetime import datetime, timezone

from core import state
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from config import APP_VERSION
from shared.health import DependencyCheck, evaluate_dependencies

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    """Health check — 503 when Qdrant (the vector store) is unreachable.

    Ollama is treated as non-critical: without it queries can't generate, but the
    service and its stored vectors are still up, so it reports ``degraded`` not down.
    Postgres persistence is optional (in-memory fallback) and not probed here.
    """

    async def _qdrant():
        # Sync client off the event loop (#211) — even the health probe shouldn't
        # block; evaluate_dependencies awaits async probes.
        await asyncio.to_thread(state.get_qdrant_client().get_collections)

    def _ollama():
        if not (state.OLLAMA_AVAILABLE and state.ollama_manager._initialized):
            raise RuntimeError("ollama not initialized")

    status, code, checks = await evaluate_dependencies(
        [
            DependencyCheck("qdrant", _qdrant, critical=True),
            DependencyCheck("ollama", _ollama, critical=False),
        ]
    )
    return JSONResponse(
        status_code=code,
        content={
            "service": "rag-pipeline",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": APP_VERSION,
            "environment": os.getenv("ENVIRONMENT", "development"),
            "knowledge_bases": len(state.knowledge_bases),
            "rag_pipelines": len(state.rag_pipelines),
            "ollama_available": state.OLLAMA_AVAILABLE,
            "ollama_initialized": state.ollama_manager._initialized,
            "checks": checks,
        },
    )


def _sentence_transformers_available() -> bool:
    """True if the cross-encoder's optional dependency is importable on this host."""
    import importlib.util

    return importlib.util.find_spec("sentence_transformers") is not None


def _bm25_available() -> bool:
    """True if rank-bm25 (the hybrid retriever's sparse backend) is installed."""
    import importlib.util

    return importlib.util.find_spec("rank_bm25") is not None


@router.get("/capabilities", tags=["System"])
async def capabilities():
    """Report which RAG methods/enhancers are active on THIS host.

    The advanced modules self-degrade by hardware: the reranker uses a cross-encoder
    when sentence-transformers (torch) is installed, otherwise a lightweight LLM
    re-rank. This endpoint makes that choice transparent (see #45).
    """
    st_available = _sentence_transformers_available()
    return {
        "methods": {
            "standard": True,
            "conversational": state.conversation_repository is not None,
            "hyde": state.hyde_expander is not None,
            "self_rag": state.self_rag_pipeline is not None,
            "auto": state.decision_engine is not None,
            "corrective": state.corrective_pipeline is not None,
        },
        "enhancers": {
            "rerank": {
                "available": state.reranker is not None,
                "backend": "cross_encoder" if st_available else "llm",
            },
            "compress": {"available": state.compressor is not None},
        },
        "retrievers": {
            # Dense (Qdrant) is always on; hybrid adds BM25 sparse when rank-bm25 is
            # present; parent_context = small-to-big (child match + neighbour window).
            "dense": {"available": True},
            "hybrid": {"available": _bm25_available()},
            "parent_child": {
                "available": True,
                "note": "small-to-big neighbour expansion via chunk_index",
            },
        },
        "optional_deps": {
            "sentence_transformers": st_available,
            "rank_bm25": _bm25_available(),
        },
    }


@router.post("/initialize", tags=["System"])
async def initialize_ollama():
    """Initialize Ollama client"""
    try:
        await state.ollama_manager.initialize()
        return {"message": "Ollama client initialized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Minder RAG Pipeline",
        "version": APP_VERSION,
        "status": "operational",
        "ollama_available": state.OLLAMA_AVAILABLE,
    }
