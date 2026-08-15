"""RAG API routes: knowledge bases, document upload, pipelines, and query."""

import asyncio
import functools
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from core import state
from core.ingestion import group_documents, ingest_document
from core.retrieval import (
    invalidate_hybrid_index,
    retrieve_hybrid,
    retrieve_parent_child,
    retrieve_relevant_documents,
)
from domain.retrievers.hybrid import BM25_AVAILABLE
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from models import (
    DocumentInfo,
    DocumentUploadResponse,
    KnowledgeBaseCreate,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    QueryRequest,
    QueryResponse,
    RAGPipelineCreate,
    RAGPipelineInfo,
    RAGPipelineResponse,
    RAGPipelineUpdate,
)
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    VectorParams,
)
from rag.model_selection import resolve_llm_model

from config import EMBEDDING_DIMENSIONS, settings
from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error
from shared.models import PaginatedList

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
    response_model=PaginatedList[KnowledgeBaseResponse],
    tags=["Knowledge Base"],
)
@router.get(
    "/knowledge-bases",
    response_model=PaginatedList[KnowledgeBaseResponse],
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def list_knowledge_bases(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List knowledge bases in the shared `{items, total, limit, offset}`
    envelope (#501; paginated via limit/offset, #147/C6).

    Served at both /v1/knowledge-bases and the legacy /knowledge-bases directly — not
    a redirect, which would drop the method/body on non-GET clients (#147).
    """
    return PaginatedList.paginate(list(state.knowledge_bases.values()), limit, offset)


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


@router.patch(
    "/v1/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
)
@router.patch(
    "/knowledge-bases/{kb_id}",
    response_model=KnowledgeBaseResponse,
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def update_knowledge_base(
    kb_id: str,
    request: KnowledgeBaseUpdate,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Update a knowledge base's mutable metadata (name / description /
    llm_model) WITHOUT touching its documents or vectors.

    Previously the only way to rename or re-describe a KB was to delete and
    recreate it — which drops the whole Qdrant collection (every uploaded
    document) and forces a full re-ingest. This edits metadata in place.
    `embedding_model` and the chunk params are immutable (see KnowledgeBaseUpdate).
    JWT-gated like delete. 404 if the KB is unknown.
    """
    kb = state.knowledge_bases.get(kb_id)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    changes = request.model_dump(exclude_unset=True)
    for field in ("name", "description", "llm_model"):
        if field in changes and changes[field] is not None:
            kb[field] = changes[field]

    if state.PG_AVAILABLE:
        try:
            await state.save_kb_to_postgres(kb_id, kb)
            logger.info(f"✅ Updated KB metadata in PostgreSQL: {kb_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to persist KB update: {e}")

    return KnowledgeBaseResponse(
        id=kb_id,
        name=kb["name"],
        description=kb["description"],
        embedding_model=kb["embedding_model"],
        llm_model=kb["llm_model"],
        document_count=kb["document_count"],
        vector_count=kb["vector_count"],
        created_at=kb["created_at"],
    )


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
async def upload_document(
    kb_id: str,
    file: UploadFile = File(...),
    build_tree: bool = Form(False),
):
    """Upload document to knowledge base.

    Served at both /v1/knowledge-bases/{kb_id}/upload and the legacy
    /knowledge-bases/{kb_id}/upload directly (and their deprecated singular
    /knowledge-base aliases) — not a redirect, which would drop the method/body on
    non-GET clients (#147).

    `build_tree` opts into RAPTOR tree construction (#487, docs/architecture/
    raptor-rag.md) on top of the normal flat chunks — off by default, since it
    adds real ingest-time LLM-summarization cost that most uploads don't want.
    """
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    kb = state.knowledge_bases[kb_id]

    # Read file — UploadFile.filename is Optional; normalise to a real string so
    # extension sniffing (.pdf/.txt/.md) and the stored payload never see None.
    # Bounded read (previously unenforced anywhere: an upload of any size got
    # fully buffered into memory) — read one byte past the limit so an
    # oversized file is caught here, before ever reaching chunk/embed/store,
    # rather than buffering the whole thing first to then reject it.
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.MAX_UPLOAD_SIZE_MB}MB upload limit",
        )
    filename = file.filename or "upload"

    return await ingest_document(kb_id, kb, filename, content, build_tree=build_tree)


@router.get(
    "/v1/knowledge-bases/{kb_id}/documents",
    response_model=PaginatedList[DocumentInfo],
    tags=["Knowledge Base"],
)
@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=PaginatedList[DocumentInfo],
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias -- also what the gateway proxy actually calls
# (it strips "v1/rag/" from "/v1/rag/knowledge-bases/{id}/documents" and forwards
# the remainder, landing on this unversioned path, not /v1/...) (#144/#147)
async def list_documents(kb_id: str):
    """List the documents uploaded into a knowledge base, one entry per
    upload (not per chunk) (#427), in the shared `{items, total, limit, offset}`
    envelope (#501). Every document is returned in one page (no server-side
    slicing here), so `limit == total` and `offset == 0`. 404 if the KB is
    unknown."""
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    client = state.get_qdrant_client()
    records: List = []
    next_offset = None
    while True:
        batch, next_offset = await asyncio.to_thread(
            client.scroll,
            collection_name=kb_id,
            limit=256,
            offset=next_offset,
            # tree_level is REQUIRED so group_documents can exclude RAPTOR
            # tree-summary nodes (tree_level > 0); without it every record arrives
            # without the field, is treated as level 0, and tree nodes inflate a
            # document's chunk_count when a tree exists (#694).
            with_payload=["source", "document_id", "uploaded_at", "tree_level"],
            with_vectors=False,
        )
        records.extend(batch)
        if next_offset is None:
            break
    documents = group_documents(records)
    return PaginatedList.from_page(
        documents, total=len(documents), limit=len(documents), offset=0
    )


@router.delete(
    "/v1/knowledge-bases/{kb_id}/documents/{document_id}",
    tags=["Knowledge Base"],
)
@router.delete(
    "/knowledge-bases/{kb_id}/documents/{document_id}",
    tags=["Knowledge Base"],
    include_in_schema=False,
)  # deprecated unversioned alias -- see list_documents' comment above
async def delete_document(
    kb_id: str,
    document_id: str,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Delete a single uploaded document's chunks/vectors from a knowledge
    base (#427), without deleting the whole KB. 404 if the KB or the
    document is unknown.

    A `legacy:<filename>` id (see DocumentInfo) deletes every chunk with that
    filename -- the same granularity available before this endpoint existed.
    """
    if kb_id not in state.knowledge_bases:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if document_id.startswith("legacy:"):
        filter_ = Filter(
            must=[
                FieldCondition(
                    key="source", match=MatchValue(value=document_id[len("legacy:") :])
                )
            ]
        )
    else:
        filter_ = Filter(
            must=[
                FieldCondition(key="document_id", match=MatchValue(value=document_id))
            ]
        )

    client = state.get_qdrant_client()
    count_result = await asyncio.to_thread(
        client.count, collection_name=kb_id, count_filter=filter_
    )
    if count_result.count == 0:
        raise HTTPException(status_code=404, detail="Document not found")

    await asyncio.to_thread(
        client.delete, collection_name=kb_id, points_selector=filter_
    )

    # New chunk composition -> drop any cached BM25 index (#45), same as upload.
    invalidate_hybrid_index(kb_id)

    kb = state.knowledge_bases[kb_id]
    kb["document_count"] = max(0, kb["document_count"] - 1)
    kb["vector_count"] = max(0, kb["vector_count"] - count_result.count)

    if state.PG_AVAILABLE:
        try:
            await state.save_kb_to_postgres(kb_id, kb)
        except Exception as e:
            logger.warning(f"⚠️  Failed to update KB in PostgreSQL: {e}")

    logger.info(f"✅ Deleted document {document_id} from KB {kb_id}")
    return {"message": "Document deleted", "id": document_id}


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


@router.get(
    "/v1/pipeline",
    response_model=PaginatedList[RAGPipelineInfo],
    tags=["Pipeline"],
)
@router.get(
    "/pipeline",
    response_model=PaginatedList[RAGPipelineInfo],
    tags=["Pipeline"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def list_rag_pipelines(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List RAG pipelines in the shared `{items, total, limit, offset}` envelope
    (#501; paginated via limit/offset, matching /knowledge-bases).

    Added in #426 -- before this, a pipeline_id only ever existed in the create
    response, with no way to recover it (clients had to track it themselves).
    """
    return PaginatedList.paginate(list(state.rag_pipelines.values()), limit, offset)


@router.get(
    "/v1/pipeline/{pipeline_id}", response_model=RAGPipelineInfo, tags=["Pipeline"]
)
@router.get(
    "/pipeline/{pipeline_id}",
    response_model=RAGPipelineInfo,
    tags=["Pipeline"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def get_rag_pipeline(pipeline_id: str):
    """Get a single RAG pipeline by id (#426). 404 if unknown."""
    pipeline = state.rag_pipelines.get(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")
    return pipeline


@router.patch(
    "/v1/pipeline/{pipeline_id}",
    response_model=RAGPipelineInfo,
    tags=["Pipeline"],
)
@router.patch(
    "/pipeline/{pipeline_id}",
    response_model=RAGPipelineInfo,
    tags=["Pipeline"],
    include_in_schema=False,
)  # deprecated unversioned alias
async def update_rag_pipeline(
    pipeline_id: str,
    request: RAGPipelineUpdate,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Update a RAG pipeline's `name` and/or `knowledge_base_ids` in place —
    no more delete + recreate just to rename one or re-point it at different
    knowledge bases. JWT-gated like delete. 404 if the pipeline (or a supplied
    KB) is unknown."""
    pipeline = state.rag_pipelines.get(pipeline_id)
    if not pipeline:
        raise HTTPException(status_code=404, detail="RAG pipeline not found")

    changes = request.model_dump(exclude_unset=True)
    if changes.get("knowledge_base_ids") is not None:
        for kb_id in changes["knowledge_base_ids"]:
            if kb_id not in state.knowledge_bases:
                raise HTTPException(
                    status_code=404, detail=f"Knowledge base {kb_id} not found"
                )
        pipeline["knowledge_base_ids"] = changes["knowledge_base_ids"]
    if changes.get("name") is not None:
        pipeline["name"] = changes["name"]

    if state.PG_AVAILABLE:
        try:
            await state.save_pipeline_to_postgres(pipeline_id, pipeline)
            logger.info(f"✅ Updated pipeline in PostgreSQL: {pipeline_id}")
        except Exception as e:
            logger.warning(f"⚠️  Failed to persist pipeline update: {e}")

    return pipeline


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
    # raptor > dense. The runner can't see this choice, so record it (and any silent
    # downgrade) here and fold it into method_details after the query runs (#138).
    want_parent = bool(getattr(request, "parent_context", False))
    want_hybrid = bool(getattr(request, "hybrid", False))
    want_raptor = getattr(request, "method", None) == "raptor"
    retrieval_notes: list[str] = []
    if want_parent:
        retrieval_strategy = "parent_context"
        retrieve_fn = retrieve_parent_child
        if want_hybrid:
            retrieval_notes.append(
                "parent_context takes precedence — hybrid flag ignored"
            )
        if want_raptor:
            retrieval_notes.append(
                "parent_context takes precedence — method=raptor ignored"
            )
    elif want_hybrid and BM25_AVAILABLE:
        retrieval_strategy = "hybrid"
        retrieve_fn = retrieve_hybrid
        if want_raptor:
            retrieval_notes.append("hybrid takes precedence — method=raptor ignored")
    elif want_raptor:
        # RAPTOR's "collapsed tree" retrieval (#487, docs/architecture/raptor-rag.md):
        # the same dense retriever, just without the tree_level=0 guard every other
        # method gets — every level (leaf chunk or LLM summary) is a plain top-k
        # candidate. A KB whose documents never opted into build_tree behaves
        # identically to standard dense retrieval here (every point is tree_level 0
        # anyway) — not an error, just nothing extra to search across.
        retrieval_strategy = "raptor"
        retrieve_fn = functools.partial(
            retrieve_relevant_documents, include_all_levels=True
        )
    else:
        retrieval_strategy = "dense"
        retrieve_fn = retrieve_relevant_documents
        if want_hybrid and not BM25_AVAILABLE:
            retrieval_notes.append(
                "hybrid requested but rank_bm25 unavailable — used dense retrieval"
            )
    if request.metadata_filter is not None:
        # Bind metadata_filter as a kwarg rather than changing retrieve_fn's shared
        # (pipeline, query, top_k) call signature — that signature is also called
        # from rag/runner.py and rag/methods/corrective.py's re-retrieve, neither of
        # which need to know about metadata_filter.
        retrieve_fn = functools.partial(
            retrieve_fn, metadata_filter=request.metadata_filter
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
    if request.metadata_filter is not None:
        method_details["metadata_filter"] = request.metadata_filter.model_dump(
            exclude_none=True
        )
    result["method_details"] = method_details
    return QueryResponse(**result)
