"""Document ingestion (upload -> chunk -> embed -> store) and document-listing
aggregation for the RAG pipeline service.

Extracted from routes/rag.py (#491, following the same "thin routes + thick
core" convention #357 established for retrieval): upload_document was a full
six-step pipeline living directly in the route handler (extract text, chunk,
time+generate embeddings, build PointStructs, upsert to Qdrant off-thread,
invalidate the BM25 cache, update KB stats, persist to Postgres) across three
separate try/except blocks, with no unit test -- coverage was integration-only,
needing the full stack running. This mirrors core/retrieval.py's own extraction
and graph-rag's routes/api.py (thin) + core/graph_retriever.py (orchestration)
split.

ingest_document() takes plain (kb_id, kb dict, filename, content bytes) rather
than a FastAPI UploadFile -- the two FastAPI-specific lines (reading the
upload, defaulting a None filename) stay in the route handler; everything
after that point is pure orchestration, independent of the request/response
layer.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from core import state
from core.retrieval import invalidate_hybrid_index
from fastapi import HTTPException
from models import DocumentInfo, DocumentUploadResponse
from qdrant_client.models import PointStruct
from rag.text_utils import chunk_text, extract_text_from_file

logger = logging.getLogger("minder.rag-pipeline")


async def ingest_document(
    kb_id: str, kb: Dict, filename: str, content: bytes
) -> DocumentUploadResponse:
    """Extract, chunk, embed, and store one uploaded document's content into
    `kb_id`'s Qdrant collection. Raises HTTPException(400) if no text could be
    extracted, HTTPException(503) if the embedding backend is unreachable."""
    text = await extract_text_from_file(content, filename)

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

    client = state.get_qdrant_client()

    # One id per upload call (not per chunk) so every chunk from THIS upload can be
    # listed/deleted together via GET|DELETE .../documents/{document_id} (#427) --
    # `source` (filename) alone can't distinguish two separate uploads of the same
    # filename.
    document_id = str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()

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
                    "document_id": document_id,
                    "uploaded_at": uploaded_at,
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
        document_id=document_id,
    )


def group_documents(records: List) -> List[DocumentInfo]:
    """Aggregate a KB's Qdrant points into one entry per uploaded document
    (#427). Points from before `document_id` existed are grouped by `source`
    (filename) instead, with a synthetic `legacy:<filename>` id -- the finest
    granularity available for that older data (see DocumentInfo's docstring)."""
    groups: Dict[str, Dict] = {}
    for record in records:
        payload = record.payload or {}
        source = payload.get("source", "")
        doc_id = payload.get("document_id") or f"legacy:{source}"
        entry = groups.setdefault(
            doc_id,
            {"document_id": doc_id, "filename": source, "chunk_count": 0},
        )
        entry["chunk_count"] += 1
        uploaded_at = payload.get("uploaded_at")
        if uploaded_at:
            entry["uploaded_at"] = uploaded_at
    return [DocumentInfo(**g) for g in groups.values()]
