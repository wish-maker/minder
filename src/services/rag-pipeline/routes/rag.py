"""RAG API routes: knowledge bases, document upload, pipelines, and query."""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from core import state
from core.retrieval import (
    invalidate_hybrid_index,
    retrieve_hybrid,
    retrieve_parent_child,
)
from domain.retrievers.hybrid import BM25_AVAILABLE
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from models import (
    DocumentUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    QueryRequest,
    QueryResponse,
    RAGPipelineCreate,
    RAGPipelineResponse,
)
from qdrant_client.models import Distance, PointStruct, VectorParams
from rag.model_selection import resolve_llm_model
from rag.text_utils import chunk_text, extract_text_from_file

from config import EMBEDDING_DIMENSIONS, settings
from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error
from shared.pagination import paginate

logger = logging.getLogger("minder.rag-pipeline")

router = APIRouter()


# Canonical paths use the plural collection `/knowledge-bases`; the singular
# `/knowledge-base[...]` forms are kept as hidden, deprecated aliases so the existing
# documented flow and clients don't break (#144).
@router.post(
    "/v1/knowledge-bases",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
)
@router.post(
    "/knowledge-bases",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
@router.post(
    "/v1/knowledge-base",
    response_model=KnowledgeBaseResponse,
    include_in_schema=False,
)
@router.post(
    "/knowledge-base",
    response_model=KnowledgeBaseResponse,
    include_in_schema=False,
)  # deprecated unversioned alias
async def create_knowledge_base(request: KnowledgeBaseCreate):
    """Create a new knowledge base.

    Served at both /v1/knowledge-bases and the legacy /knowledge-bases directly (and
    their deprecated singular /knowledge-base aliases) — not a redirect, which would
    drop the method/body on non-GET clients (#147).
    """
    kb_id = str(uuid.uuid4())

    # Get embedding dimension
    embed_dim = EMBEDDING_DIMENSIONS.get(request.embedding_model, 768)

    # Stamp once so the stored and returned created_at match (#140).
    created_at = datetime.now(timezone.utc).isoformat()
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
        "created_at": created_at,
    }

    # Create Qdrant collection
    client = state.get_qdrant_client()

    try:
        # QdrantClient is synchronous; run its calls off the event loop so a slow
        # collection op doesn't stall every other concurrent request (#211).
        await asyncio.to_thread(
            client.create_collection,
            collection_name=kb_id,
            vectors_config=VectorParams(size=embed_dim, distance=Distance.COSINE),
        )
        logger.info(f"✅ Created Qdrant collection: {kb_id} (dim={embed_dim})")
    except Exception as e:
        logger.error(f"❌ Failed to create Qdrant collection: {e}")
        raise backend_http_error(e, "Creating vector collection")

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
        created_at=created_at,
    )


@router.get(
    "/v1/knowledge-bases",
    response_model=List[KnowledgeBaseResponse],
    tags=["Knowledge Base"],
)
@router.get(
    "/knowledge-bases",
    response_model=List[KnowledgeBaseResponse],
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def list_knowledge_bases(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List knowledge bases (paginated via limit/offset, #147/C6).

    Served at both /v1/knowledge-bases and the legacy /knowledge-bases directly — not
    a redirect, which would drop the method/body on non-GET clients (#147).
    """
    page, _total = paginate(list(state.knowledge_bases.values()), limit, offset)
    return page


@router.get(
    "/v1/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
)
@router.get(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
@router.get(
    "/v1/knowledge-base/{kb_id}",
    response_model=KnowledgeBaseResponse,
    include_in_schema=False,
)
@router.get(
    "/knowledge-base/{kb_id}",
    response_model=KnowledgeBaseResponse,
    include_in_schema=False,
)  # deprecated unversioned alias
async def get_knowledge_base(kb_id: str):
    """Get a single knowledge base by id.

    Served at both /v1/knowledge-bases/{kb_id} and the legacy /knowledge-bases/{kb_id}
    directly (and their deprecated singular /knowledge-base aliases) — not a
    redirect, which would drop the method/body on non-GET clients (#147).
    """
    kb = state.knowledge_bases.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.delete("/v1/knowledge-bases/{kb_id}", tags=["Knowledge Base"])
@router.delete(
    "/knowledge-bases/{kb_id}",
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
@router.delete("/v1/knowledge-base/{kb_id}", include_in_schema=False)
@router.delete(
    "/knowledge-base/{kb_id}", include_in_schema=False
)  # deprecated unversioned alias
async def delete_knowledge_base(
    kb_id: str,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Delete a knowledge base: its Qdrant collection, its PostgreSQL row, and the
    in-memory entry. Idempotent-ish — 404 if the KB is unknown.

    Served at both /v1/knowledge-bases/{kb_id} and the legacy /knowledge-bases/{kb_id}
    directly (and their deprecated singular /knowledge-base aliases) — not a
    redirect, which would drop the method/body on non-GET clients (#147).
    """
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Drop the Qdrant collection (best-effort — may already be gone).
    try:
        await asyncio.to_thread(
            state.get_qdrant_client().delete_collection, collection_name=kb_id
        )
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
    "/v1/knowledge-bases/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    tags=["Knowledge Base"],
)
@router.post(
    "/knowledge-bases/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
@router.post(
    "/v1/knowledge-base/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    include_in_schema=False,
)
@router.post(
    "/knowledge-base/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    include_in_schema=False,
)  # deprecated unversioned alias
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """Upload document to knowledge base.

    Served at both /v1/knowledge-bases/{kb_id}/upload and the legacy
    /knowledge-bases/{kb_id}/upload directly (and their deprecated singular
    /knowledge-base aliases) — not a redirect, which would drop the method/body on
    non-GET clients (#147).
    """
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    kb = state.knowledge_bases[kb_id]

    # Read file
    content = await file.read()

    # UploadFile.filename is Optional; normalise to a real string so extension
    # sniffing (.pdf/.txt/.md) and the stored payload never see None.
    filename = file.filename or "upload"

    # Extract text
    text = await extract_text_from_file(content, filename)

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
                    "source": filename,
                    "chunk_index": i,
                    "kb_id": kb_id,
                },
            )
        )

    # Upsert points to Qdrant using PointStruct list. Off the event loop (#211): a
    # large upload's upsert is the worst blocker on the sync client.
    await asyncio.to_thread(
        client.upsert,
        collection_name=kb_id,
        points=points,
    )

    # New chunks landed → drop any cached BM25 index so the next hybrid query
    # rebuilds it over the full, current set (#45).
    invalidate_hybrid_index(kb_id)

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

    logger.info(f"✅ Uploaded {filename} to KB {kb_id}: {len(chunks)} chunks")

    state.documents_processed_total.labels(status="success").inc()

    return DocumentUploadResponse(
        message="Document uploaded successfully",
        chunks_processed=len(chunks),
        vectors_created=len(chunks),
        filename=filename,
    )


@router.post("/v1/pipeline", response_model=RAGPipelineResponse, tags=["Pipeline"])
@router.post(
    "/pipeline",
    response_model=RAGPipelineResponse,
    tags=["Pipeline"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def create_rag_pipeline(request: RAGPipelineCreate):
    """Create a RAG pipeline.

    Served at both /v1/pipeline and the legacy /pipeline directly — not a redirect,
    which would drop the method/body on non-GET clients (#147).
    """
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
        "created_at": datetime.now(timezone.utc).isoformat(),
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

    return RAGPipelineResponse(
        pipeline_id=pipeline_id,
        name=request.name,
        knowledge_base_ids=request.knowledge_base_ids,
        created_at=state.rag_pipelines[pipeline_id]["created_at"],
    )


@router.delete("/v1/pipeline/{pipeline_id}", tags=["Pipeline"])
@router.delete(
    "/pipeline/{pipeline_id}",
    tags=["Pipeline"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def delete_rag_pipeline(
    pipeline_id: str,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Delete a RAG pipeline (its PostgreSQL row + the in-memory entry). The KBs it
    referenced are left intact. 404 if the pipeline is unknown.

    Served at both /v1/pipeline/{pipeline_id} and the legacy /pipeline/{pipeline_id}
    directly — not a redirect, which would drop the method/body on non-GET clients
    (#147).
    """
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
    "/v1/pipeline/{pipeline_id}/query",
    response_model=QueryResponse,
    tags=["Pipeline"],
)
@router.post(
    "/pipeline/{pipeline_id}/query",
    response_model=QueryResponse,
    tags=["Pipeline"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def query_rag_pipeline(pipeline_id: str, request: QueryRequest):
    """Query a RAG pipeline.

    Served at both /v1/pipeline/{pipeline_id}/query and the legacy
    /pipeline/{pipeline_id}/query directly — not a redirect, which would drop the
    method/body on non-GET clients (#147).
    """
    if pipeline_id not in state.rag_pipelines:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    pipeline = state.rag_pipelines[pipeline_id]
    # Retrieval strategy is chosen here as a drop-in retrieve variant (same signature)
    # so the runner/methods stay retrieval-agnostic (#45). parent_context > hybrid >
    # dense. The runner can't see this choice, so record it (and any silent downgrade)
    # here and fold it into method_details after the query runs (#138).
    want_parent = bool(getattr(request, "parent_context", False))
    want_hybrid = bool(getattr(request, "hybrid", False))
    retrieval_notes: list[str] = []
    if want_parent:
        retrieval_strategy = "parent_context"
        retrieve_fn = retrieve_parent_child
        if want_hybrid:
            retrieval_notes.append(
                "parent_context takes precedence — hybrid flag ignored"
            )
    elif want_hybrid and BM25_AVAILABLE:
        retrieval_strategy = "hybrid"
        retrieve_fn = retrieve_hybrid
    else:
        retrieval_strategy = "dense"
        retrieve_fn = retrieve_relevant_documents
        if want_hybrid and not BM25_AVAILABLE:
            retrieval_notes.append(
                "hybrid requested but rank_bm25 unavailable — used dense retrieval"
            )
    components = state.RagComponents(
        ollama_manager=state.ollama_manager,
        retrieve=retrieve_fn,
        hyde_expander=state.hyde_expander,
        self_rag_pipeline=state.self_rag_pipeline,
        decision_engine=state.decision_engine,
        corrective_pipeline=state.corrective_pipeline,
        reranker=state.reranker,
        compressor=state.compressor,
        conversation_repository=state.conversation_repository,
        gen_timer=state.llm_generation_duration,
    )
    try:
        result = await state.run_query(
            pipeline=pipeline,
            pipeline_id=pipeline_id,
            request=request,
            llm_model=resolve_llm_model(
                request.llm_model,
                pipeline,
                state.knowledge_bases,
                settings.OLLAMA_LLM_MODEL,
            ),
            generation_config=pipeline.get("generation_config", {}),
            components=components,
        )
    except state.GenerationError as e:
        # LLM backend failed to produce an answer — surface a real 503 rather than a
        # 200 whose "answer" is a leaked exception string (#232), matching the
        # embedding-failure 503 (#77). The exception's own message (from
        # generate_response's error path) is safe to expose — no secrets, just what
        # ollama/the failover router reported — and is more useful than a fixed
        # generic string (e.g. it says whether failover served this off the
        # internal fallback while the primary is down, #249).
        detail = str(e) or (
            "LLM backend unavailable — could not generate an answer. Check that "
            "OLLAMA_BASE_URL is reachable and the model is available."
        )
        raise HTTPException(status_code=503, detail=detail)
    # Annotate the retrieval strategy the runner is blind to, plus any silent downgrade.
    method_details = dict(result.get("method_details") or {})
    method_details["retrieval"] = retrieval_strategy
    if retrieval_notes:
        method_details.setdefault("degraded", []).extend(retrieval_notes)
    result["method_details"] = method_details
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
            search_result = await asyncio.to_thread(
                client.query_points,
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
