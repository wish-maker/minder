"""
Minder RAG Pipeline Service - Production Ready
Real Ollama integration with proper embedding generation and LLM inference
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from models import (
    DocumentUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    QueryRequest,
    QueryResponse,
    RAGPipelineCreate,
)
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from rag.ollama_manager import OLLAMA_AVAILABLE, OllamaManager
from rag.text_utils import chunk_text, extract_text_from_file

from config import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_LLM_MODEL,
    EMBEDDING_DIMENSIONS,
    OLLAMA_HOST,
    QDRANT_HOST,
    QDRANT_PORT,
)

_LOG_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logger = logging.getLogger("minder.rag-pipeline")

# Configure logging to output logs to stdout at the configured level
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setLevel(_LOG_LEVEL)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(_LOG_LEVEL)
    # Surface logs from the RAG method packages (rag/, domain/, agent/) with the
    # same handler, so the extracted modules log consistently with main.
    for _pkg in ("rag", "domain", "agent"):
        _pkg_logger = logging.getLogger(_pkg)
        if not _pkg_logger.handlers:
            _pkg_logger.addHandler(handler)
            _pkg_logger.setLevel(_LOG_LEVEL)

# ============================================================================
# FastAPI App
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize storage/Ollama on startup (see body); no explicit shutdown work."""
    logger.info("🚀 Starting RAG Pipeline service...")
    logger.info(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    logger.info(f"Ollama: {OLLAMA_HOST}")
    logger.info(f"Default LLM: {DEFAULT_LLM_MODEL}")
    logger.info(f"Default Embedding: {DEFAULT_EMBEDDING_MODEL}")

    # Load data from PostgreSQL if available
    if PG_AVAILABLE:
        try:
            # Initialize database schema (will preserve existing data)
            await initialize_schema()

            loaded_kbs = await load_kb_from_postgres()
            knowledge_bases.update(loaded_kbs)
            logger.info(f"✅ Loaded {len(loaded_kbs)} knowledge bases from PostgreSQL")

            loaded_pipelines = await load_pipelines_from_postgres()
            rag_pipelines.update(loaded_pipelines)
            logger.info(
                f"✅ Loaded {len(loaded_pipelines)} RAG pipelines from PostgreSQL"
            )

            # Initialize ConversationRepository for conversational RAG
            global conversation_repository
            if CONVERSATION_REPO_AVAILABLE and pg_client.pg_pool:
                try:
                    conversation_repository = ConversationRepository(pg_client.pg_pool)
                    logger.info("✅ ConversationRepository initialized")
                except Exception as e:
                    logger.error(f"❌ Failed to initialize ConversationRepository: {e}")
                    conversation_repository = None
            else:
                logger.warning(
                    "⚠️  ConversationRepository not available (pg_pool or module missing)"
                )
                conversation_repository = None
        except Exception as e:
            logger.error(f"❌ Failed to load from PostgreSQL: {e}")
    else:
        logger.info("ℹ️  Using in-memory storage (PostgreSQL not available)")

    # Initialize Ollama manager
    if OLLAMA_AVAILABLE:
        try:
            await ollama_manager.initialize()
            logger.info("✅ Ollama manager initialized successfully")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama manager: {e}")
            # Don't fail startup, just log the error
    else:
        logger.warning("⚠️  Ollama not available, RAG features will be limited")

    yield


app = FastAPI(
    title="Minder RAG Pipeline",
    description="Production RAG Pipeline with Ollama integration",
    version="1.0.0",
    lifespan=lifespan,
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

knowledge_bases: Dict[str, Dict[str, Any]] = {}
rag_pipelines: Dict[str, Dict[str, Any]] = {}

# Global conversation repository instance
conversation_repository: Optional[ConversationRepository] = None


# ============================================================================
# Ollama Client Management
# ============================================================================

# Global Ollama manager (OllamaManager lives in rag/ollama_manager.py)
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
from rag.runner import RagComponents, run_query  # noqa: E402

# ============================================================================
# Qdrant Client Management
# ============================================================================


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client"""
    return QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    return {
        "service": "rag-pipeline",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": os.getenv("ENVIRONMENT", "development"),
        "knowledge_bases": len(knowledge_bases),
        "rag_pipelines": len(rag_pipelines),
        "ollama_available": OLLAMA_AVAILABLE,
        "ollama_initialized": ollama_manager._initialized,
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/initialize", tags=["System"])
async def initialize_ollama():
    """Initialize Ollama client"""
    try:
        await ollama_manager.initialize()
        return {"message": "Ollama client initialized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/knowledge-base", response_model=KnowledgeBaseResponse, tags=["Knowledge Base"]
)
async def create_knowledge_base(request: KnowledgeBaseCreate):
    """Create a new knowledge base"""
    import uuid

    kb_id = str(uuid.uuid4())

    # Get embedding dimension
    embed_dim = EMBEDDING_DIMENSIONS.get(request.embedding_model, 768)

    knowledge_bases[kb_id] = {
        "id": kb_id,
        "name": request.name,
        "description": request.description,
        "embedding_model": request.embedding_model,
        "llm_model": request.llm_model,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
        "document_count": 0,
        "vector_count": 0,
        "created_at": datetime.now().isoformat(),
    }

    # Create Qdrant collection
    client = get_qdrant_client()

    try:
        client.create_collection(
            collection_name=kb_id,
            vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
        )
        logger.info(f"✅ Created Qdrant collection: {kb_id} (dim={embed_dim})")
    except Exception as e:
        logger.error(f"❌ Failed to create Qdrant collection: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to create collection: {str(e)}"
        )

    # Save to PostgreSQL if available
    if PG_AVAILABLE:
        try:
            await save_kb_to_postgres(kb_id, knowledge_bases[kb_id])
            logger.info(f"✅ Saved KB to PostgreSQL: {kb_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to save KB to PostgreSQL: {e}")

    return KnowledgeBaseResponse(
        id=kb_id,
        name=request.name,
        description=request.description,
        embedding_model=request.embedding_model,
        llm_model=request.llm_model,
        document_count=0,
        vector_count=0,
        created_at=datetime.now().isoformat(),
    )


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
    """Upload document to knowledge base"""
    if kb_id not in knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    kb = knowledge_bases[kb_id]

    # Read file
    content = await file.read()

    # Extract text
    text = await extract_text_from_file(content, file.filename)

    # Chunk text
    chunks = chunk_text(
        text, chunk_size=kb["chunk_size"], chunk_overlap=kb["chunk_overlap"]
    )

    if not chunks:
        raise HTTPException(status_code=400, detail="No text content extracted")

    # Generate embeddings
    with embedding_generation_duration.labels(model=kb["embedding_model"]).time():
        embeddings = await ollama_manager.generate_embeddings(
            chunks, model=kb["embedding_model"]
        )

    # Store in Qdrant
    client = get_qdrant_client()

    points = []
    import uuid

    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),  # Generate proper UUID
                vector=embedding,
                payload={
                    "text": chunk,
                    "source": file.filename,
                    "chunk_index": i,
                    "kb_id": kb_id,
                },
            )
        )

    # Upsert points to Qdrant using PointStruct list
    client.upsert(
        collection_name=kb_id,
        points=points,
    )

    # Update knowledge base stats
    kb["document_count"] += 1
    kb["vector_count"] += len(chunks)

    # Save updated KB to PostgreSQL if available
    if PG_AVAILABLE:
        try:
            await save_kb_to_postgres(kb_id, kb)
            logger.info(f"✅ Updated KB in PostgreSQL: {kb_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to update KB in PostgreSQL: {e}")

    logger.info(f"✅ Uploaded {file.filename} to KB {kb_id}: {len(chunks)} chunks")

    documents_processed_total.labels(status="success").inc()

    return DocumentUploadResponse(
        message="Document uploaded successfully",
        chunks_processed=len(chunks),
        vectors_created=len(chunks),
        filename=file.filename,
    )


@app.post("/pipeline", tags=["Pipeline"])
async def create_rag_pipeline(request: RAGPipelineCreate):
    """Create a RAG pipeline"""
    import uuid

    pipeline_id = str(uuid.uuid4())

    # Validate knowledge bases exist
    for kb_id in request.knowledge_base_ids:
        if kb_id not in knowledge_bases:
            raise HTTPException(
                status_code=404, detail=f"Knowledge base {kb_id} not found"
            )

    rag_pipelines[pipeline_id] = {
        "id": pipeline_id,
        "name": request.name,
        "knowledge_base_ids": request.knowledge_base_ids,
        "retrieval_config": request.retrieval_config,
        "generation_config": request.generation_config,
        "created_at": datetime.now().isoformat(),
    }

    # Save to PostgreSQL if available
    if PG_AVAILABLE:
        try:
            await save_pipeline_to_postgres(pipeline_id, rag_pipelines[pipeline_id])
            logger.info(f"✅ Saved pipeline to PostgreSQL: {pipeline_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to save pipeline to PostgreSQL: {e}")

    logger.info(f"✅ Created RAG pipeline: {pipeline_id}")

    return {
        "message": "RAG pipeline created successfully",
        "pipeline_id": pipeline_id,
    }


@app.post(
    "/pipeline/{pipeline_id}/query", response_model=QueryResponse, tags=["Pipeline"]
)
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest):
    """Query a RAG pipeline"""
    if pipeline_id not in rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    pipeline = rag_pipelines[pipeline_id]
    components = RagComponents(
        ollama_manager=ollama_manager,
        retrieve=retrieve_relevant_documents,
        hyde_expander=hyde_expander,
        self_rag_pipeline=self_rag_pipeline,
        decision_engine=decision_engine,
        conversation_repository=conversation_repository,
        gen_timer=llm_generation_duration,
    )
    result = await run_query(
        pipeline=pipeline,
        pipeline_id=pipeline_id,
        request=request,
        llm_model=pipeline.get("llm_model") or DEFAULT_LLM_MODEL,
        generation_config=pipeline.get("generation_config", {}),
        components=components,
    )
    return QueryResponse(**result)


async def retrieve_relevant_documents(
    pipeline: Dict, question: str, top_k: int
) -> Dict:
    """Retrieve relevant documents from knowledge bases"""
    client = get_qdrant_client()

    # Get embedding model from first KB
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = knowledge_bases[first_kb_id]["embedding_model"]

    # Create embedding for question
    question_embeddings = await ollama_manager.generate_embeddings(
        [question], model=embed_model
    )
    question_embedding = question_embeddings[0]

    # Search across all knowledge bases
    all_results = []
    for kb_id in pipeline["knowledge_base_ids"]:
        try:
            search_result = client.query_points(
                collection_name=kb_id,
                query=question_embedding,
                limit=top_k,
            )
            # Extract points from QueryResponse
            results = search_result.points
            all_results.extend(results)
        except Exception as e:
            logger.warning(f"⚠️  Search failed for KB {kb_id}: {e}")

    # Sort by score and take top_k
    all_results = sorted(all_results, key=lambda x: x.score, reverse=True)[:top_k]

    # Extract context
    context = "\n\n".join([r.payload.get("text", "") for r in all_results])

    return {
        "context": context,
        "sources": [
            {
                "text": r.payload.get("text", ""),
                "source": r.payload.get("source", ""),
                "score": r.score,
            }
            for r in all_results
        ],
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Minder RAG Pipeline",
        "version": app.version,
        "status": "operational",
        "ollama_available": OLLAMA_AVAILABLE,
    }


# ============================================================================
# Startup Event
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
