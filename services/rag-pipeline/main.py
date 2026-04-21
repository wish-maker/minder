"""
Minder RAG Pipeline Service
Handles knowledge base creation, retrieval, and generation
"""

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Dict, List, Any
from datetime import datetime
import logging
import os

logger = logging.getLogger(__name__)

# Configuration from environment variables
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")
QDRANT_PORT = os.getenv("QDRANT_PORT", "6333")
MODEL_MANAGEMENT_URL = os.getenv("MODEL_MANAGEMENT_URL", "http://minder-model-management:8005")

# Initialize FastAPI
app = FastAPI(
    title="Minder RAG Pipeline",
    description="RAG Pipeline for knowledge management",
    version="2.0.0",
)


# Pydantic models
class KnowledgeBaseCreate(BaseModel):
    """Knowledge base creation request"""

    name: str
    description: str
    embedding_model: str = "text-embedding-3-small"
    chunk_size: int = 512
    chunk_overlap: int = 50


class KnowledgeBaseResponse(BaseModel):
    """Knowledge base response"""

    id: str
    name: str
    description: str
    document_count: int
    vector_count: int
    created_at: str


class RAGPipelineCreate(BaseModel):
    """RAG Pipeline creation request"""

    name: str
    knowledge_base_ids: List[str]
    retrieval_config: Dict[str, Any]
    generation_config: Dict[str, Any]


class QueryRequest(BaseModel):
    """Query request"""

    question: str
    pipeline_id: str
    top_k: int = 5


class QueryResponse(BaseModel):
    """Query response"""

    answer: str
    sources: List[Dict[str, Any]]
    confidence: float


# In-memory knowledge base storage (use PostgreSQL in production)
knowledge_bases: Dict[str, Dict[str, Any]] = {}
rag_pipelines: Dict[str, Dict[str, Any]] = {}


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "knowledge_bases": len(knowledge_bases),
        "rag_pipelines": len(rag_pipelines),
    }


# Create knowledge base
@app.post("/knowledge-base", response_model=KnowledgeBaseResponse, tags=["Knowledge Base"])
async def create_knowledge_base(request: KnowledgeBaseCreate):
    """Create a new knowledge base"""
    import uuid

    kb_id = str(uuid.uuid4())

    knowledge_bases[kb_id] = {
        "id": kb_id,
        "name": request.name,
        "description": request.description,
        "embedding_model": request.embedding_model,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
        "document_count": 0,
        "vector_count": 0,
        "created_at": datetime.now().isoformat(),
    }

    # Create Qdrant collection
    from qdrant_client import QdrantClient

    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    try:
        client.create_collection(
            collection_name=kb_id,
            vectors_config={
                "size": 1536,  # OpenAI embedding size
                "distance": "Cosine",
            },
        )
        logger.info(f"Created Qdrant collection: {kb_id}")
    except Exception as e:
        logger.error(f"Failed to create Qdrant collection: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {str(e)}")

    return KnowledgeBaseResponse(
        id=kb_id,
        name=request.name,
        description=request.description,
        document_count=0,
        vector_count=0,
        created_at=datetime.now().isoformat(),
    )


# List knowledge bases
@app.get("/knowledge-bases", tags=["Knowledge Base"])
async def list_knowledge_bases():
    """List all knowledge bases"""
    return list(knowledge_bases.values())


# Upload document to knowledge base
@app.post("/knowledge-base/{kb_id}/upload", tags=["Knowledge Base"])
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """Upload document to knowledge base"""
    if kb_id not in knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Read file
    content = await file.read()

    # Extract text based on file type
    text = await extract_text_from_file(content, file.filename)

    # Chunk text
    from langchain.text_splitter import RecursiveCharacterTextSplitter

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=knowledge_bases[kb_id]["chunk_size"],
        chunk_overlap=knowledge_bases[kb_id]["chunk_overlap"],
    )
    chunks = text_splitter.split_text(text)

    # Create embeddings
    embeddings = await create_embeddings(chunks)

    # Store in Qdrant
    from qdrant_client import QdrantClient

    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    points = []
    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
        points.append(
            {
                "id": f"{kb_id}_{file.filename}_{i}",
                "vector": embedding,
                "payload": {
                    "text": chunk,
                    "source": file.filename,
                    "chunk_index": i,
                },
            }
        )

    client.upsert(
        collection_name=kb_id,
        points=points,
    )

    # Update knowledge base stats
    knowledge_bases[kb_id]["document_count"] += 1
    knowledge_bases[kb_id]["vector_count"] += len(chunks)

    logger.info(f"Uploaded {file.filename} to KB {kb_id}: {len(chunks)} chunks")

    return {
        "message": "Document uploaded successfully",
        "chunks_processed": len(chunks),
        "vectors_created": len(chunks),
    }


# Create RAG pipeline
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

    logger.info(f"Created RAG pipeline: {pipeline_id}")

    return {
        "message": "RAG pipeline created successfully",
        "pipeline_id": pipeline_id,
    }


# Query RAG pipeline
@app.post("/pipeline/{pipeline_id}/query", response_model=QueryResponse, tags=["Pipeline"])
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest):
    """Query a RAG pipeline"""
    if pipeline_id not in rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    pipeline = rag_pipelines[pipeline_id]

    # Retrieve relevant documents
    context = await retrieve_relevant_documents(
        pipeline,
        request.question,
        request.top_k,
    )

    # Generate answer
    answer = await generate_answer(
        pipeline,
        request.question,
        context,
    )

    return QueryResponse(
        answer=answer["text"],
        sources=context["sources"],
        confidence=answer.get("confidence", 0.8),
    )


# Helper functions
async def extract_text_from_file(content: bytes, filename: str) -> str:
    """Extract text from file based on type"""
    from pypdf import PdfReader
    import io

    if filename.endswith(".pdf"):
        pdf_file = io.BytesIO(content)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    else:
        # Assume text file
        return content.decode("utf-8")


async def create_embeddings(texts: List[str]) -> List[List[float]]:
    """Create embeddings for texts"""
    # Use OpenAI API or local model
    # This is a placeholder - implement actual embedding generation
    import numpy as np

    return [np.random.rand(1536).tolist() for _ in texts]


async def retrieve_relevant_documents(pipeline: Dict, question: str, top_k: int) -> Dict:
    """Retrieve relevant documents from knowledge bases"""
    from qdrant_client import QdrantClient

    client = QdrantClient(url=f"http://{QDRANT_HOST}:{QDRANT_PORT}")

    # Create embedding for question
    question_embedding = await create_embeddings([question])
    question_embedding = question_embedding[0]

    # Search across all knowledge bases
    all_results = []
    for kb_id in pipeline["knowledge_base_ids"]:
        results = client.search(
            collection_name=kb_id,
            query_vector=question_embedding,
            limit=top_k,
        )
        all_results.extend(results)

    # Sort by score and take top_k
    all_results = sorted(all_results, key=lambda x: x["score"], reverse=True)[:top_k]

    # Extract context
    context = "\n\n".join([r["payload"]["text"] for r in all_results])

    return {
        "context": context,
        "sources": [
            {
                "text": r["payload"]["text"],
                "source": r["payload"]["source"],
                "score": r["score"],
            }
            for r in all_results
        ],
    }


async def generate_answer(pipeline: Dict, question: str, context: Dict) -> Dict:
    """Generate answer using LLM"""
    # Use Ollama or OpenAI for generation
    # This is a placeholder - implement actual LLM call
    return {
        "text": f"Based on the context, here's the answer to: {question}",
        "confidence": 0.85,
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Minder RAG Pipeline",
        "version": "2.0.0",
        "status": "operational",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8004)
