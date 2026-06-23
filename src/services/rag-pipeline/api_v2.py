"""
RAG Pipeline API V2 - Clean Architecture Implementation

Thin API layer that delegates to service layer.
All business logic is in services/, all data access in repositories/.
"""

import logging

from fastapi import APIRouter, HTTPException, UploadFile

# Service layer imports
from services.knowledge_base_service import KnowledgeBaseService
from services.retrieval_service import RetrievalService

# Infrastructure imports
from infrastructure.ollama import OllamaManager
from infrastructure.resource_manager import Pi4ResourceManager

# API Models (shared)
from api.models import (
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    QueryRequest,
    QueryResponse,
    DocumentUploadResponse,
)

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v2", tags=["RAG Pipeline V2"])

# ============================================================================
# Dependency Injection (would use a DI container in production)
# ============================================================================

# Global infrastructure components
# In production: initialize at startup and inject via dependencies
_resource_manager: Pi4ResourceManager = None
_ollama_manager: OllamaManager = None
_knowledge_base_service: KnowledgeBaseService = None
_retrieval_service: RetrievalService = None


def get_resource_manager() -> Pi4ResourceManager:
    """Get resource manager instance"""
    global _resource_manager
    if _resource_manager is None:
        _resource_manager = Pi4ResourceManager()
    return _resource_manager


def get_ollama_manager() -> OllamaManager:
    """Get Ollama manager instance"""
    global _ollama_manager
    if _ollama_manager is None:
        _ollama_manager = OllamaManager()
    return _ollama_manager


def get_knowledge_base_service() -> KnowledgeBaseService:
    """Get knowledge base service instance"""
    global _knowledge_base_service
    if _knowledge_base_service is None:
        _knowledge_base_service = KnowledgeBaseService(
            ollama_manager=get_ollama_manager(), resource_manager=get_resource_manager()
        )
    return _knowledge_base_service


def get_retrieval_service() -> RetrievalService:
    """Get retrieval service instance"""
    global _retrieval_service
    if _retrieval_service is None:
        _retrieval_service = RetrievalService(
            ollama_manager=get_ollama_manager(),
            qdrant_client=None,  # Would initialize properly
            resource_manager=get_resource_manager(),
            hyde_expander=None,  # Optional components
            hybrid_searcher=None,
            reranker=None,
            crag_retriever=None,
            parent_child_retriever=None,
            context_compressor=None,
        )
    return _retrieval_service


# ============================================================================
# Knowledge Base Endpoints (Thin - delegate to service)
# ============================================================================


@router.post("/knowledge-base", response_model=KnowledgeBaseResponse)
async def create_knowledge_base(request: KnowledgeBaseCreate) -> KnowledgeBaseResponse:
    """
    Create a new knowledge base

    Thin endpoint that delegates to KnowledgeBaseService.
    All validation and business logic is in the service layer.
    """
    try:
        logger.info(f"Creating knowledge base: {request.name}")

        service = get_knowledge_base_service()
        result = await service.create_knowledge_base(
            name=request.name,
            description=request.description,
            embedding_model=request.embedding_model,
            llm_model=request.llm_model,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            parent_child_enabled=request.parent_child_enabled,
        )

        logger.info(f"Knowledge base created: {result.id}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-bases", tags=["Knowledge Base"])
async def list_knowledge_bases():
    """List all knowledge bases"""
    try:
        service = get_knowledge_base_service()
        return await service.list_knowledge_bases()

    except Exception as e:
        logger.error(f"Failed to list knowledge bases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/knowledge-base/{kb_id}/upload", response_model=DocumentUploadResponse)
async def upload_document(kb_id: str, file: UploadFile):
    """
    Upload document to knowledge base

    Thin endpoint that delegates to KnowledgeBaseService.
    All file processing, chunking, embedding is in the service layer.
    """
    try:
        logger.info(f"Uploading {file.filename} to KB {kb_id}")

        # Read file content
        content = await file.read()

        service = get_knowledge_base_service()
        result = await service.upload_document(
            kb_id=kb_id, filename=file.filename, content=content
        )

        logger.info(f"Document uploaded: {result.chunks_processed} chunks")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to upload document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Query Endpoints (Thin - delegate to service)
# ============================================================================


@router.post("/pipeline/{pipeline_id}/query", response_model=QueryResponse)
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest) -> QueryResponse:
    """
    Query a RAG pipeline

    Thin endpoint that delegates to RetrievalService.
    All retrieval logic, reranking, compression is in the service layer.
    """
    try:
        logger.info(f"Querying pipeline {pipeline_id}: {request.question[:50]}...")

        service = get_retrieval_service()

        # Resource check
        resource_manager = get_resource_manager()
        await resource_manager.throttle_if_needed()

        # Delegate to service layer
        result = await service.retrieve_and_generate(
            pipeline_id=pipeline_id,
            question=request.question,
            top_k=request.top_k,
            knowledge_bases={},  # Would fetch from repository
        )

        logger.info(f"Query completed: {len(result.sources)} sources")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Health & Metrics (Thin - system status)
# ============================================================================


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "rag-pipeline-v2",
        "architecture": "clean",
        "components": {
            "api": "operational",
            "services": "operational",
            "infrastructure": "operational",
        },
    }


@router.get("/metrics")
async def get_metrics():
    """Get service metrics"""
    try:
        resource_manager = get_resource_manager()
        return await resource_manager.check_resources()
    except Exception as e:
        logger.error(f"Failed to get metrics: {e}")
        return {"status": "unavailable"}
