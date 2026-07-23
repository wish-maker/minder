"""System & observability routes: /health, /metrics, /initialize, / (root)."""

import os
from datetime import datetime

import state
from fastapi import APIRouter, HTTPException

from config import APP_VERSION

router = APIRouter()


@router.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    return {
        "service": "rag-pipeline",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": APP_VERSION,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "knowledge_bases": len(state.knowledge_bases),
        "rag_pipelines": len(state.rag_pipelines),
        "ollama_available": state.OLLAMA_AVAILABLE,
        "ollama_initialized": state.ollama_manager._initialized,
    }


def _sentence_transformers_available() -> bool:
    """True if the cross-encoder's optional dependency is importable on this host."""
    import importlib.util

    return importlib.util.find_spec("sentence_transformers") is not None


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
        "optional_deps": {
            "sentence_transformers": st_available,
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
