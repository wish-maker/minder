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
