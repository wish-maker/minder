"""
Minder RAG Pipeline Service - Production Ready
Real Ollama integration with proper embedding generation and LLM inference
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Response, UploadFile
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from pydantic import BaseModel

# Ollama client for real embeddings and LLM
try:
    from ollama import AsyncClient

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("ollama package not installed. Install with: pip install ollama")

# Qdrant client
from qdrant_client import QdrantClient
from qdrant_client.models import Batch, Distance, PointStruct, VectorParams

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
MODEL_MANAGEMENT_URL = os.getenv("MODEL_MANAGEMENT_URL", "http://minder-model-management:8005")

# Default models (can be overridden per knowledge base)
DEFAULT_EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
DEFAULT_LLM_MODEL = os.getenv("OLLAMA_LLM_MODEL", "llama3.2")

# Embedding dimensions (depends on model)
EMBEDDING_DIMENSIONS = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "all-minilm": 384,
}

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Minder RAG Pipeline",
    description="Production RAG Pipeline with Ollama integration",
    version="3.0.0",
)


# ============================================================================
# Prometheus Metrics
# ============================================================================

http_requests_total = Counter("http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"])

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

knowledge_bases_total = Gauge("knowledge_bases_total", "Total number of knowledge bases")

documents_processed_total = Counter("documents_processed_total", "Total documents processed", ["status"])

embedding_generation_duration = Histogram(
    "embedding_generation_duration_seconds", "Time to generate embeddings", ["model"]
)

llm_generation_duration = Histogram("llm_generation_duration_seconds", "Time to generate LLM response", ["model"])


# ============================================================================
# Pydantic Models
# ============================================================================


class KnowledgeBaseCreate(BaseModel):
    """Knowledge base creation request"""

    name: str
    description: str
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    llm_model: str = DEFAULT_LLM_MODEL
    chunk_size: int = 512
    chunk_overlap: int = 50


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response"""

    id: str
    name: str
    description: str
    embedding_model: str
    llm_model: str
    document_count: int
    vector_count: int
    created_at: str


class RAGPipelineCreate(BaseModel):
    """RAG Pipeline creation request"""

    name: str
    knowledge_base_ids: List[str]
    retrieval_config: Dict[str, Any] = {}
    generation_config: Dict[str, Any] = {}


class QueryRequest(BaseModel):
    """Query request"""

    question: str
    pipeline_id: str
    top_k: int = 5
    stream: bool = False


class QueryResponse(BaseModel):
    """Query response"""

    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    model_used: str
    tokens_used: Optional[int] = None


class DocumentUploadResponse(BaseModel):
    """Document upload response"""

    message: str
    chunks_processed: int
    vectors_created: int
    filename: str


# ============================================================================
# In-Memory Storage (use PostgreSQL in production)
# ============================================================================

knowledge_bases: Dict[str, Dict[str, Any]] = {}
rag_pipelines: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# Ollama Client Management
# ============================================================================


class OllamaManager:
    """Manage Ollama client connections"""

    def __init__(self):
        self.client: Optional[AsyncClient] = None
        self.embed_client: Optional[AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Ollama clients"""
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama package not installed")

        try:
            self.client = AsyncClient(host=OLLAMA_HOST)
            self.embed_client = AsyncClient(host=OLLAMA_HOST)

            # Test connection
            await self._test_connection()
            self._initialized = True
            logger.info(f"✅ Ollama client initialized: {OLLAMA_HOST}")

        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama client: {e}")
            raise

    async def _test_connection(self):
        """Test Ollama connection"""
        try:
            # List available models to verify connection
            models = await self.client.list()
            logger.info(
                f"✅ Ollama connection verified. Available models: {[m['name'] for m in models.get('models', [])]}"
            )
        except Exception as e:
            logger.warning(f"⚠️  Ollama connection test failed: {e}")
            # Don't fail - models might not be pulled yet

    async def ensure_model(self, model_name: str):
        """Ensure model is available, pull if necessary"""
        try:
            models = await self.client.list()
            available = [m["name"] for m in models.get("models", [])]

            # Check if model exists with any version tag
            model_exists = any(
                model_name in available_model or available_model.startswith(model_name + ":")
                for available_model in available
            )

            if not model_exists:
                logger.info(f"📥 Pulling model: {model_name}")
                await self.client.pull(model_name)
                logger.info(f"✅ Model pulled: {model_name}")
            else:
                logger.debug(f"✅ Model {model_name} already available")

        except Exception as e:
            logger.warning(f"⚠️  Could not verify/pull model {model_name}: {e}")

    async def generate_embeddings(self, texts: List[str], model: str = DEFAULT_EMBEDDING_MODEL) -> List[List[float]]:
        """Generate embeddings using Ollama"""
        if not self._initialized:
            await self.initialize()

        await self.ensure_model(model)

        embeddings = []
        for text in texts:
            try:
                response = await self.embed_client.embeddings(model=model, prompt=text)
                embedding = response.get("embedding", [])
                embeddings.append(embedding)
            except Exception as e:
                logger.error(f"❌ Embedding generation failed: {e}")
                # Return zero vector as fallback
                dim = EMBEDDING_DIMENSIONS.get(model, 768)
                embeddings.append([0.0] * dim)

        return embeddings

    async def generate_response(
        self,
        prompt: str,
        model: str = DEFAULT_LLM_MODEL,
        context: str = "",
        temperature: float = 0.7,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """Generate response using Ollama LLM"""
        if not self._initialized:
            await self.initialize()

        await self.ensure_model(model)

        # Build full prompt with context
        full_prompt = self._build_rag_prompt(prompt, context)

        try:
            response = await self.client.generate(
                model=model,
                prompt=full_prompt,
                stream=stream,
                options={
                    "temperature": temperature,
                    "num_predict": 2000,  # Max tokens
                },
            )

            return {
                "text": response.get("response", ""),
                "model": model,
                "context": context,
                "tokens_used": response.get("prompt_eval_count", 0) + response.get("eval_count", 0),
            }

        except Exception as e:
            logger.error(f"❌ LLM generation failed: {e}")
            return {
                "text": f"Error generating response: {str(e)}",
                "model": model,
                "context": context,
                "tokens_used": 0,
            }

    def _build_rag_prompt(self, question: str, context: str) -> str:
        """Build RAG prompt with context"""
        if context:
            return f"""Context information is below.
---------------------
{context}
---------------------

Given the context information and not prior knowledge, answer the query.
Query: {question}

Answer:"""
        else:
            return f"Answer the following question: {question}"


# Global Ollama manager
ollama_manager = OllamaManager()


# ============================================================================
# Qdrant Client Management
# ============================================================================


def get_qdrant_client() -> QdrantClient:
    """Get Qdrant client"""
    return QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")


# ============================================================================
# Text Processing
# ============================================================================


async def extract_text_from_file(content: bytes, filename: str) -> str:
    """Extract text from file based on type"""
    import io

    from pypdf import PdfReader

    if filename.endswith(".pdf"):
        pdf_file = io.BytesIO(content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    elif filename.endswith(".txt") or filename.endswith(".md"):
        return content.decode("utf-8")
    else:
        # Default: try UTF-8 decode
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("latin-1")


def chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> List[str]:
    """Chunk text into smaller pieces"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks = text_splitter.split_text(text)
    return chunks


# ============================================================================
# API Endpoints
# ============================================================================


@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
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


@app.post("/knowledge-base", response_model=KnowledgeBaseResponse, tags=["Knowledge Base"])
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
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {str(e)}")

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


@app.post("/knowledge-base/{kb_id}/upload", response_model=DocumentUploadResponse, tags=["Knowledge Base"])
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
    chunks = chunk_text(text, chunk_size=kb["chunk_size"], chunk_overlap=kb["chunk_overlap"])

    if not chunks:
        raise HTTPException(status_code=400, detail="No text content extracted")

    # Generate embeddings
    with embedding_generation_duration.labels(model=kb["embedding_model"]).time():
        embeddings = await ollama_manager.generate_embeddings(chunks, model=kb["embedding_model"])

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
            raise HTTPException(status_code=404, detail=f"Knowledge base {kb_id} not found")

    rag_pipelines[pipeline_id] = {
        "id": pipeline_id,
        "name": request.name,
        "knowledge_base_ids": request.knowledge_base_ids,
        "retrieval_config": request.retrieval_config,
        "generation_config": request.generation_config,
        "created_at": datetime.now().isoformat(),
    }

    logger.info(f"✅ Created RAG pipeline: {pipeline_id}")

    return {
        "message": "RAG pipeline created successfully",
        "pipeline_id": pipeline_id,
    }


@app.post("/pipeline/{pipeline_id}/query", response_model=QueryResponse, tags=["Pipeline"])
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest):
    """Query a RAG pipeline"""
    if pipeline_id not in rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    pipeline = rag_pipelines[pipeline_id]

    # Retrieve relevant documents
    context_result = await retrieve_relevant_documents(
        pipeline,
        request.question,
        request.top_k,
    )

    # Generate answer
    with llm_generation_duration.labels(model=pipeline.get("llm_model", DEFAULT_LLM_MODEL)).time():
        answer_result = await ollama_manager.generate_response(
            prompt=request.question,
            context=context_result["context"],
            **pipeline.get("generation_config", {}),
        )

    return QueryResponse(
        answer=answer_result["text"],
        sources=context_result["sources"],
        confidence=0.85,  # TODO: Calculate actual confidence from scores
        model_used=answer_result.get("model", "unknown"),
        tokens_used=answer_result.get("tokens_used"),
    )


async def retrieve_relevant_documents(pipeline: Dict, question: str, top_k: int) -> Dict:
    """Retrieve relevant documents from knowledge bases"""
    client = get_qdrant_client()

    # Get embedding model from first KB
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = knowledge_bases[first_kb_id]["embedding_model"]

    # Create embedding for question
    question_embeddings = await ollama_manager.generate_embeddings([question], model=embed_model)
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
        "version": "3.0.0",
        "status": "operational",
        "ollama_available": OLLAMA_AVAILABLE,
    }


# ============================================================================
# Startup Event
# ============================================================================


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("🚀 Starting RAG Pipeline service...")
    logger.info(f"Qdrant: {QDRANT_HOST}:{QDRANT_PORT}")
    logger.info(f"Ollama: {OLLAMA_HOST}")
    logger.info(f"Default LLM: {DEFAULT_LLM_MODEL}")
    logger.info(f"Default Embedding: {DEFAULT_EMBEDDING_MODEL}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
