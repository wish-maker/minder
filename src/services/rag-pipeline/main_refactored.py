"""
RAG Pipeline Service - Clean Architecture Implementation

This refactored version uses the professional clean architecture layers
that are already prepared. All business logic is in services/, all
algorithms in domain/, all external dependencies in infrastructure/.

This file is now a thin API layer that delegates to service layer.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

# Legacy imports (will be removed after full migration)
from corrective_rag import CorrectiveRetriever
from domain.compressors.contextual import ContextualCompressor

# Domain Layer
from domain.expansion.hyde import HyDEQueryExpander
from domain.pipelines.self_rag import SelfRAGPipeline
from domain.rerankers.cross_encoder import CrossEncoderReranker
from domain.retrievers.hybrid import HybridSearchRetriever
from domain.retrievers.parent_child import ParentChildRetriever
from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from infrastructure.cache import EmbeddingCache

# Infrastructure Layer
from infrastructure.ollama import OLLAMA_AVAILABLE, OllamaManager
from infrastructure.resource_manager import Pi4ResourceManager
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel

# Service Layer
from services.knowledge_base_service import KnowledgeBaseService
from services.retrieval_service import RetrievalService

# ============================================================================
# Clean Architecture Imports
# ============================================================================


logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")

DEFAULT_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
DEFAULT_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")

EMBEDDING_DIMENSIONS = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
}

# ============================================================================
# Global Components (Dependency Injection in production)
# ============================================================================

# Infrastructure
pi4_manager = Pi4ResourceManager()
embedding_cache = EmbeddingCache(max_size=500)
ollama_manager = OllamaManager()

# Domain Components (optional, injected into services)
hyde_expander = HyDEQueryExpander()
hybrid_searcher = HybridSearchRetriever(alpha=0.5)
parent_child_retriever = ParentChildRetriever()
context_compressor = ContextualCompressor(max_tokens=2000, compression_ratio=0.3)
reranker = CrossEncoderReranker()
self_rag_pipeline = SelfRAGPipeline(max_iterations=2, quality_threshold=0.7)
crag_retriever = CorrectiveRetriever()

# Services (will be initialized at startup)
knowledge_base_service: Optional[KnowledgeBaseService] = None
retrieval_service: Optional[RetrievalService] = None

# Legacy storage (will migrate to PostgreSQL)
knowledge_bases: Dict[str, Dict[str, Any]] = {}
rag_pipelines: Dict[str, Dict[str, Any]] = {}

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Minder RAG Pipeline",
    description="Production RAG Pipeline with Clean Architecture",
    version="2.0.0",
)

# ============================================================================
# Prometheus Metrics
# ============================================================================

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)
documents_processed_total = Counter(
    "documents_processed_total", "Total documents processed", ["status"]
)

# ============================================================================
# Lifespan Management
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan with clean initialization"""
    # Startup
    logger.info("🚀 Starting RAG Pipeline service (Clean Architecture)...")

    try:
        # Initialize infrastructure
        if OLLAMA_AVAILABLE:
            await ollama_manager.initialize()
            logger.info("✅ Ollama manager initialized")
        else:
            logger.warning("⚠️ Ollama not available")

        # Initialize services with dependency injection
        global knowledge_base_service, retrieval_service

        # Import Qdrant client here to avoid early import errors
        from qdrant_client import QdrantClient

        qdrant_client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

        logger.info(f"✅ Qdrant client initialized: {QDRANT_HOST}:{QDRANT_PORT}")

        knowledge_base_service = KnowledgeBaseService(
            ollama_manager=ollama_manager,
            qdrant_client=qdrant_client,
            parent_child_chunker=None,  # Optional
        )

        retrieval_service = RetrievalService(
            ollama_manager=ollama_manager,
            qdrant_client=qdrant_client,
            resource_manager=pi4_manager,
            hyde_expander=hyde_expander,
            hybrid_searcher=hybrid_searcher,
            reranker=reranker,
            crag_retriever=crag_retriever,
            parent_child_retriever=parent_child_retriever,
            context_compressor=context_compressor,
        )

        logger.info("✅ Services initialized with clean architecture")

    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        # Don't fail startup, degrade gracefully

    yield

    # Shutdown
    logger.info("🛑 Shutting down RAG Pipeline service...")


app = FastAPI(
    title="Minder RAG Pipeline",
    description="Production RAG Pipeline with Clean Architecture",
    version="2.0.0",
    lifespan=lifespan,
)

# ============================================================================
# Pydantic Models
# ============================================================================


class KnowledgeBaseCreate(BaseModel):
    name: str
    description: str
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    chunk_size: int = 512
    chunk_overlap: int = 50
    parent_child_enabled: bool = False


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str
    embedding_model: str
    llm_model: str
    document_count: int
    vector_count: int
    created_at: str


class QueryRequest(BaseModel):
    question: str
    pipeline_id: str
    top_k: int = 5
    stream: bool = False


class QueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    model_used: str
    tokens_used: Optional[int] = None


class DocumentUploadResponse(BaseModel):
    message: str
    chunks_processed: int
    vectors_created: int
    filename: str


# ============================================================================
# Health & Metrics
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check with service status"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "architecture": "clean",
        "ollama_available": OLLAMA_AVAILABLE,
        "services_initialized": knowledge_base_service is not None,
        "knowledge_bases": len(knowledge_bases),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# Knowledge Base Endpoints (Thin - Delegate to Service)
# ============================================================================


@app.post(
    "/knowledge-base", response_model=KnowledgeBaseResponse, tags=["Knowledge Base"]
)
async def create_knowledge_base(request: KnowledgeBaseCreate):
    """
    Create knowledge base using service layer

    Thin endpoint - all business logic in KnowledgeBaseService
    """
    if knowledge_base_service is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    try:
        logger.info(f"Creating knowledge base: {request.name}")

        result = await knowledge_base_service.create_knowledge_base(
            name=request.name,
            description=request.description,
            embedding_model=request.embedding_model,
            llm_model=request.llm_model,
            chunk_size=request.chunk_size,
            chunk_overlap=request.chunk_overlap,
            parent_child_enabled=request.parent_child_enabled,
        )

        # Also store in legacy dict for backward compatibility
        knowledge_bases[result.id] = {
            "id": result.id,
            "name": result.name,
            "description": result.description,
            "embedding_model": result.embedding_model,
            "llm_model": result.llm_model,
            "document_count": result.document_count,
            "vector_count": result.vector_count,
            "created_at": result.created_at,
        }

        logger.info(f"✅ Knowledge base created: {result.id}")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Failed to create knowledge base: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/knowledge-bases", tags=["Knowledge Base"])
async def list_knowledge_bases():
    """List all knowledge bases"""
    return list(knowledge_bases.values())


@app.post(
    "/knowledge-base/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    tags=["Knowledge Base"],
)
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """
    Upload document using service layer

    Thin endpoint - all processing in KnowledgeBaseService
    """
    if knowledge_base_service is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    if kb_id not in knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    try:
        logger.info(f"Uploading {file.filename} to KB {kb_id}")

        content = await file.read()

        result = await knowledge_base_service.upload_document(
            kb_id=kb_id, filename=file.filename, content=content
        )

        # Update legacy stats
        if kb_id in knowledge_bases:
            knowledge_bases[kb_id]["document_count"] += 1
            knowledge_bases[kb_id]["vector_count"] += result.chunks_processed

        logger.info(f"✅ Document uploaded: {result.chunks_processed} chunks")
        documents_processed_total.labels(status="success").inc()
        return result

    except ValueError as e:
        documents_processed_total.labels(status="failed").inc()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        documents_processed_total.labels(status="error").inc()
        logger.error(f"❌ Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Query Endpoints (Thin - Delegate to Service)
# ============================================================================


@app.post(
    "/pipeline/{pipeline_id}/query", response_model=QueryResponse, tags=["Pipeline"]
)
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest):
    """
    Query RAG pipeline using service layer

    Thin endpoint - all retrieval logic in RetrievalService
    """
    if retrieval_service is None:
        raise HTTPException(status_code=503, detail="Services not initialized")

    if pipeline_id not in rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    try:
        logger.info(f"Querying pipeline {pipeline_id}: {request.question[:50]}...")

        # Resource check
        await pi4_manager.throttle_if_needed()

        # Delegate to service layer
        result = await retrieval_service.retrieve_and_generate(
            pipeline_id=pipeline_id,
            question=request.question,
            top_k=request.top_k,
            knowledge_bases=knowledge_bases,
        )

        logger.info(f"✅ Query completed: {len(result.sources)} sources")
        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Legacy Endpoints (Will be migrated to services)
# ============================================================================


@app.post("/pipeline", tags=["Pipeline"])
async def create_rag_pipeline(request: Dict):
    """Create RAG pipeline (legacy - will migrate to service)"""
    import uuid

    pipeline_id = str(uuid.uuid4())

    rag_pipelines[pipeline_id] = {
        "id": pipeline_id,
        "name": request.get("name", "default"),
        "knowledge_base_ids": request.get("knowledge_base_ids", []),
        "created_at": datetime.now().isoformat(),
    }

    logger.info(f"✅ Pipeline created: {pipeline_id}")
    return {"pipeline_id": pipeline_id, "message": "Pipeline created"}


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Minder RAG Pipeline",
        "version": app.version,
        "architecture": "clean",
        "status": "operational",
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
