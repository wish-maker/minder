"""RAG API routes: knowledge bases, document upload, pipelines, and query."""

import logging
import uuid
from datetime import datetime
from typing import Dict

import state
from fastapi import APIRouter, File, HTTPException, UploadFile
from models import (
    DocumentUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    QueryRequest,
    QueryResponse,
    RAGPipelineCreate,
)
from qdrant_client.models import Distance, PointStruct, VectorParams
from rag.text_utils import chunk_text, extract_text_from_file

from config import DEFAULT_LLM_MODEL, EMBEDDING_DIMENSIONS

logger = logging.getLogger("minder.rag-pipeline")

router = APIRouter()


@router.post(
    "/knowledge-base", response_model=KnowledgeBaseResponse, tags=["Knowledge Base"]
)
async def create_knowledge_base(request: KnowledgeBaseCreate):
    """Create a new knowledge base"""
    kb_id = str(uuid.uuid4())

    # Get embedding dimension
    embed_dim = EMBEDDING_DIMENSIONS.get(request.embedding_model, 768)

    state.knowledge_bases[kb_id] = {
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
    client = state.get_qdrant_client()

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
    if state.PG_AVAILABLE:
        try:
            await state.save_kb_to_postgres(kb_id, state.knowledge_bases[kb_id])
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


@router.get("/knowledge-bases", tags=["Knowledge Base"])
async def list_knowledge_bases():
    """List all knowledge bases"""
    return list(state.knowledge_bases.values())


@router.get("/knowledge-base/{kb_id}", tags=["Knowledge Base"])
async def get_knowledge_base(kb_id: str):
    """Get a single knowledge base by id."""
    kb = state.knowledge_bases.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.delete("/knowledge-base/{kb_id}", tags=["Knowledge Base"])
async def delete_knowledge_base(kb_id: str):
    """Delete a knowledge base: its Qdrant collection, its PostgreSQL row, and the
    in-memory entry. Idempotent-ish — 404 if the KB is unknown."""
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Drop the Qdrant collection (best-effort — may already be gone).
    try:
        state.get_qdrant_client().delete_collection(collection_name=kb_id)
        logger.info(f"✅ Deleted Qdrant collection: {kb_id}")
    except Exception as e:
        logger.warning(f"⚠️  Failed to delete Qdrant collection {kb_id}: {e}")

    if state.PG_AVAILABLE:
        try:
            await state.delete_kb_from_postgres(kb_id)
        except Exception as e:
            logger.warning(f"⚠️  Failed to delete KB from PostgreSQL: {e}")

    state.knowledge_bases.pop(kb_id, None)
    logger.info(f"✅ Deleted knowledge base: {kb_id}")
    return {"message": "Knowledge base deleted", "id": kb_id}


@router.post(
    "/knowledge-base/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    tags=["Knowledge Base"],
)
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """Upload document to knowledge base"""
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    kb = state.knowledge_bases[kb_id]

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

    # Generate embeddings — fail loudly if the backend is unreachable rather than
    # storing zero-vectors, which would make the document silently unsearchable (#77).
    try:
        with state.embedding_generation_duration.labels(
            model=kb["embedding_model"]
        ).time():
            embeddings = await state.ollama_manager.generate_embeddings(
                chunks, model=kb["embedding_model"]
            )
    except Exception as e:
        state.documents_processed_total.labels(status="failed").inc()
        raise HTTPException(
            status_code=503,
            detail=(
                "Embedding backend unavailable — document was NOT indexed. Check that "
                f"OLLAMA_BASE_URL is reachable from the containers. ({e})"
            ),
        )

    # Store in Qdrant
    client = state.get_qdrant_client()

    points = []
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
    if state.PG_AVAILABLE:
        try:
            await state.save_kb_to_postgres(kb_id, kb)
            logger.info(f"✅ Updated KB in PostgreSQL: {kb_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to update KB in PostgreSQL: {e}")

    logger.info(f"✅ Uploaded {file.filename} to KB {kb_id}: {len(chunks)} chunks")

    state.documents_processed_total.labels(status="success").inc()

    return DocumentUploadResponse(
        message="Document uploaded successfully",
        chunks_processed=len(chunks),
        vectors_created=len(chunks),
        filename=file.filename,
    )


@router.post("/pipeline", tags=["Pipeline"])
async def create_rag_pipeline(request: RAGPipelineCreate):
    """Create a RAG pipeline"""
    pipeline_id = str(uuid.uuid4())

    # Validate knowledge bases exist
    for kb_id in request.knowledge_base_ids:
        if kb_id not in state.knowledge_bases:
            raise HTTPException(
                status_code=404, detail=f"Knowledge base {kb_id} not found"
            )

    state.rag_pipelines[pipeline_id] = {
        "id": pipeline_id,
        "name": request.name,
        "knowledge_base_ids": request.knowledge_base_ids,
        "retrieval_config": request.retrieval_config,
        "generation_config": request.generation_config,
        "created_at": datetime.now().isoformat(),
    }

    # Save to PostgreSQL if available
    if state.PG_AVAILABLE:
        try:
            await state.save_pipeline_to_postgres(
                pipeline_id, state.rag_pipelines[pipeline_id]
            )
            logger.info(f"✅ Saved pipeline to PostgreSQL: {pipeline_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to save pipeline to PostgreSQL: {e}")

    logger.info(f"✅ Created RAG pipeline: {pipeline_id}")

    return {
        "message": "RAG pipeline created successfully",
        "pipeline_id": pipeline_id,
    }


@router.delete("/pipeline/{pipeline_id}", tags=["Pipeline"])
async def delete_rag_pipeline(pipeline_id: str):
    """Delete a RAG pipeline (its PostgreSQL row + the in-memory entry). The KBs it
    referenced are left intact. 404 if the pipeline is unknown."""
    if pipeline_id not in state.rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    if state.PG_AVAILABLE:
        try:
            await state.delete_pipeline_from_postgres(pipeline_id)
        except Exception as e:
            logger.warning(f"⚠️  Failed to delete pipeline from PostgreSQL: {e}")

    state.rag_pipelines.pop(pipeline_id, None)
    logger.info(f"✅ Deleted RAG pipeline: {pipeline_id}")
    return {"message": "RAG pipeline deleted", "id": pipeline_id}


@router.post(
    "/pipeline/{pipeline_id}/query", response_model=QueryResponse, tags=["Pipeline"]
)
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest):
    """Query a RAG pipeline"""
    if pipeline_id not in state.rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    pipeline = state.rag_pipelines[pipeline_id]
    components = state.RagComponents(
        ollama_manager=state.ollama_manager,
        retrieve=retrieve_relevant_documents,
        hyde_expander=state.hyde_expander,
        self_rag_pipeline=state.self_rag_pipeline,
        decision_engine=state.decision_engine,
        conversation_repository=state.conversation_repository,
        gen_timer=state.llm_generation_duration,
    )
    result = await state.run_query(
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
    client = state.get_qdrant_client()

    # Get embedding model from first KB
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = state.knowledge_bases[first_kb_id]["embedding_model"]

    # Create embedding for question — fail loudly if the backend is unreachable
    # rather than searching with a garbage vector (#77).
    try:
        question_embeddings = await state.ollama_manager.generate_embeddings(
            [question], model=embed_model
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=(
                "Embedding backend unavailable — cannot answer query. Check that "
                f"OLLAMA_BASE_URL is reachable from the containers. ({e})"
            ),
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
