"""RAG API routes: knowledge bases, document upload, pipelines, and query."""

import logging
import uuid
from datetime import datetime
from typing import Dict, List

from core import state
from domain.retrievers.hybrid import BM25_AVAILABLE, HybridSearchRetriever
from fastapi import APIRouter, File, HTTPException, UploadFile
from models import (
    DocumentUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    QueryRequest,
    QueryResponse,
    RAGPipelineCreate,
    RAGPipelineResponse,
)
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    VectorParams,
)
from rag.text_utils import chunk_text, extract_text_from_file

from config import DEFAULT_LLM_MODEL, EMBEDDING_DIMENSIONS

logger = logging.getLogger("minder.rag-pipeline")

router = APIRouter()


# Canonical paths use the plural collection `/knowledge-bases`; the singular
# `/knowledge-base[...]` forms are kept as hidden, deprecated aliases so the existing
# documented flow and clients don't break (#144).
@router.post(
    "/knowledge-bases", response_model=KnowledgeBaseResponse, tags=["Knowledge Base"]
)
@router.post(
    "/knowledge-base",
    response_model=KnowledgeBaseResponse,
    include_in_schema=False,
)
async def create_knowledge_base(request: KnowledgeBaseCreate):
    """Create a new knowledge base"""
    kb_id = str(uuid.uuid4())

    # Get embedding dimension
    embed_dim = EMBEDDING_DIMENSIONS.get(request.embedding_model, 768)

    # Stamp once so the stored and returned created_at match (#140).
    created_at = datetime.now().isoformat()
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
        created_at=created_at,
    )


@router.get(
    "/knowledge-bases",
    response_model=List[KnowledgeBaseResponse],
    tags=["Knowledge Base"],
)
async def list_knowledge_bases():
    """List all knowledge bases"""
    return list(state.knowledge_bases.values())


@router.get(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
)
@router.get(
    "/knowledge-base/{kb_id}",
    response_model=KnowledgeBaseResponse,
    include_in_schema=False,
)
async def get_knowledge_base(kb_id: str):
    """Get a single knowledge base by id."""
    kb = state.knowledge_bases.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")
    return kb


@router.delete("/knowledge-bases/{kb_id}", tags=["Knowledge Base"])
@router.delete("/knowledge-base/{kb_id}", include_in_schema=False)
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
    "/knowledge-bases/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    tags=["Knowledge Base"],
)
@router.post(
    "/knowledge-base/{kb_id}/upload",
    response_model=DocumentUploadResponse,
    include_in_schema=False,
)
async def upload_document(kb_id: str, file: UploadFile = File(...)):
    """Upload document to knowledge base"""
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

    # Upsert points to Qdrant using PointStruct list
    client.upsert(
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


@router.post("/pipeline", response_model=RAGPipelineResponse, tags=["Pipeline"])
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

    return RAGPipelineResponse(
        pipeline_id=pipeline_id,
        name=request.name,
        knowledge_base_ids=request.knowledge_base_ids,
        created_at=state.rag_pipelines[pipeline_id]["created_at"],
    )


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
    result = await state.run_query(
        pipeline=pipeline,
        pipeline_id=pipeline_id,
        request=request,
        llm_model=pipeline.get("llm_model") or DEFAULT_LLM_MODEL,
        generation_config=pipeline.get("generation_config", {}),
        components=components,
    )
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


# ── Hybrid retrieval (dense + BM25 sparse), #45 ────────────────────────────────
# One process-local HybridSearchRetriever holds the in-memory BM25 index per KB. The
# index is built lazily from the chunks already stored in Qdrant (so it survives
# restarts — it just rebuilds on the next hybrid query) and dropped when a KB gains
# documents (see upload) so the next query rebuilds it fresh.
_hybrid = HybridSearchRetriever()


def invalidate_hybrid_index(kb_id: str) -> None:
    """Drop the cached BM25 index for a KB so the next hybrid query rebuilds it."""
    _hybrid.sparse_index.pop(kb_id, None)
    _hybrid.documents.pop(kb_id, None)


def _ensure_bm25_index(client, kb_id: str) -> None:
    """Build the BM25 index for `kb_id` from stored Qdrant chunks if not cached."""
    if kb_id in _hybrid.sparse_index:
        return
    docs = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=kb_id,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            docs.append(
                {
                    "_id": str(p.id),
                    "text": p.payload.get("text", ""),
                    "source": p.payload.get("source", ""),
                }
            )
        if offset is None or len(docs) >= 10000:
            break
    if docs:
        _hybrid.index_documents(kb_id, docs)


async def retrieve_hybrid(pipeline: Dict, question: str, top_k: int) -> Dict:
    """Retrieve via dense + BM25 hybrid scoring (same shape as the dense retriever)."""
    client = state.get_qdrant_client()
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = state.knowledge_bases[first_kb_id]["embedding_model"]

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

    merged: list = []
    for kb_id in pipeline["knowledge_base_ids"]:
        try:
            dense = client.query_points(
                collection_name=kb_id,
                query=question_embedding,
                limit=top_k * 3,  # wider candidate set so BM25 can surface keyword hits
            ).points
        except Exception as e:
            logger.warning(f"⚠️  Hybrid search failed for KB {kb_id}: {e}")
            continue

        _ensure_bm25_index(client, kb_id)
        docmap = {d["_id"]: d for d in _hybrid.documents.get(kb_id, [])}
        for r in dense:  # dense-only hits may not be in the scrolled snapshot
            did = r.payload.get("_id", str(r.id))
            docmap.setdefault(
                did,
                {
                    "text": r.payload.get("text", ""),
                    "source": r.payload.get("source", ""),
                },
            )

        pairs = await _hybrid.hybrid_search(
            kb_id, question_embedding, question, dense, top_k
        )
        for did, score in pairs:
            d = docmap.get(did, {})
            merged.append(
                {
                    "text": d.get("text", ""),
                    "source": d.get("source", ""),
                    "score": float(score),
                }
            )

    merged = sorted(merged, key=lambda s: s["score"], reverse=True)[:top_k]
    context = "\n\n".join(s["text"] for s in merged)
    return {"context": context, "sources": merged}


# ── Parent-child / small-to-big retrieval (#45) ────────────────────────────────
# Match precise (small) child chunks via dense search, then RETURN each with its
# neighbouring chunks (same source, adjacent chunk_index) so the LLM gets fuller
# "parent" context. Reuses the chunk_index already stored in every payload — no
# special ingest-time hierarchy needed.
PARENT_WINDOW = 1  # neighbours on each side → a 2*W+1 chunk parent


async def retrieve_parent_child(pipeline: Dict, question: str, top_k: int) -> Dict:
    """Retrieve child chunks, expand each to its neighbour window (same doc/source)."""
    client = state.get_qdrant_client()
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = state.knowledge_bases[first_kb_id]["embedding_model"]

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

    sources: list = []
    seen: set = (
        set()
    )  # (kb_id, source, center chunk_index) → dedupe overlapping windows
    for kb_id in pipeline["knowledge_base_ids"]:
        try:
            hits = client.query_points(
                collection_name=kb_id, query=question_embedding, limit=top_k
            ).points
        except Exception as e:
            logger.warning(f"⚠️  Parent-child search failed for KB {kb_id}: {e}")
            continue

        for h in hits:
            src = h.payload.get("source", "")
            ci = h.payload.get("chunk_index")
            if ci is None:  # older doc without chunk_index → return the child as-is
                sources.append(
                    {"text": h.payload.get("text", ""), "source": src, "score": h.score}
                )
                continue
            key = (kb_id, src, ci)
            if key in seen:
                continue
            seen.add(key)

            # Fetch the neighbour window (same source, chunk_index within ±W).
            flt = Filter(
                must=[
                    FieldCondition(key="source", match=MatchValue(value=src)),
                    FieldCondition(
                        key="chunk_index",
                        range=Range(gte=ci - PARENT_WINDOW, lte=ci + PARENT_WINDOW),
                    ),
                ]
            )
            try:
                neighbours, _ = client.scroll(
                    collection_name=kb_id,
                    scroll_filter=flt,
                    limit=2 * PARENT_WINDOW + 1,
                    with_payload=True,
                    with_vectors=False,
                )
            except Exception as e:
                logger.warning(f"⚠️  Neighbour fetch failed ({src}#{ci}): {e}")
                neighbours = []

            ordered = sorted(
                neighbours or [h], key=lambda p: p.payload.get("chunk_index", 0)
            )
            parent_text = "\n".join(p.payload.get("text", "") for p in ordered)
            sources.append(
                {
                    "text": parent_text,
                    "source": src,
                    "score": h.score,
                    "context_type": "parent",
                    "child_chunk_index": ci,
                }
            )

    sources = sorted(sources, key=lambda s: s["score"], reverse=True)[:top_k]
    context = "\n\n".join(s["text"] for s in sources)
    return {"context": context, "sources": sources}
