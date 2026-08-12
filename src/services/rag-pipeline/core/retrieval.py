"""Hybrid and parent-child retrieval orchestration for the RAG pipeline service.

Extracted from routes/rag.py (#357): these functions wire together app-level state
(core.state — the Qdrant client, ollama_manager, knowledge_bases) with the
domain-pure HybridSearchRetriever (domain/retrievers/hybrid.py) to answer a query.
They live in `core/` rather than `domain/retrievers/` because they touch
state/Qdrant/HTTPException directly — domain/retrievers/hybrid.py is explicitly
documented as "a domain component with NO external dependencies," and moving
route-orchestration logic in there would violate that. This mirrors graph-rag's
routes/api.py (thin HTTP layer) + core/graph_retriever.py (orchestration) split.
"""

import asyncio
import logging
from typing import Dict, Optional

from core import state
from domain.retrievers.hybrid import HybridSearchRetriever
from fastapi import HTTPException
from models import MetadataFilter
from qdrant_client.models import FieldCondition, Filter, MatchValue, Range

logger = logging.getLogger(__name__)


def build_metadata_filter(
    metadata_filter: Optional[MetadataFilter],
) -> Optional[Filter]:
    """Build a Qdrant `Filter` from a `MetadataFilter` (source/document_id exact
    match, ANDed). Returns None when nothing is set, so every call site can pass
    the result straight through as `query_filter`/`scroll_filter` unconditionally."""
    if metadata_filter is None:
        return None
    conditions = []
    if metadata_filter.source is not None:
        conditions.append(
            FieldCondition(key="source", match=MatchValue(value=metadata_filter.source))
        )
    if metadata_filter.document_id is not None:
        conditions.append(
            FieldCondition(
                key="document_id", match=MatchValue(value=metadata_filter.document_id)
            )
        )
    return Filter(must=conditions) if conditions else None


def _matches_metadata_filter(
    doc: Dict, metadata_filter: Optional[MetadataFilter]
) -> bool:
    """Post-filter for hybrid's sparse side: BM25 scores the whole cached corpus
    (see _ensure_bm25_index), so a metadata_filter applied only to the dense Qdrant
    call would still let a sparse-only hit from a filtered-out document through.
    Checked against `doc` dicts built from Qdrant payloads (source/document_id)."""
    if metadata_filter is None:
        return True
    if (
        metadata_filter.source is not None
        and doc.get("source") != metadata_filter.source
    ):
        return False
    if (
        metadata_filter.document_id is not None
        and doc.get("document_id") != metadata_filter.document_id
    ):
        return False
    return True


# One process-local HybridSearchRetriever holds the in-memory BM25 index per KB. The
# index is built lazily from the chunks already stored in Qdrant (so it survives
# restarts — it just rebuilds on the next hybrid query) and dropped when a KB gains
# documents (see routes/rag.py's upload) so the next query rebuilds it fresh.
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
                    "document_id": p.payload.get("document_id", ""),
                }
            )
        if offset is None or len(docs) >= 10000:
            break
    if docs:
        _hybrid.index_documents(kb_id, docs)


async def retrieve_hybrid(
    pipeline: Dict,
    question: str,
    top_k: int,
    metadata_filter: Optional[MetadataFilter] = None,
) -> Dict:
    """Retrieve via dense + BM25 hybrid scoring (same shape as the dense retriever).

    metadata_filter is applied to the dense Qdrant call directly, AND as a
    post-filter on the merged results — the BM25 corpus (_ensure_bm25_index) is
    cached per-KB and unfiltered, so a sparse-only hit from a document the filter
    excludes must still be dropped before returning (see _matches_metadata_filter).
    """
    client = state.get_qdrant_client()
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = state.knowledge_bases[first_kb_id]["embedding_model"]
    qdrant_filter = build_metadata_filter(metadata_filter)

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
            dense = (
                await asyncio.to_thread(
                    client.query_points,
                    collection_name=kb_id,
                    query=question_embedding,
                    query_filter=qdrant_filter,
                    # wider candidate set so BM25 can surface keyword hits
                    limit=top_k * 3,
                )
            ).points
        except Exception as e:
            logger.warning(f"⚠️  Hybrid search failed for KB {kb_id}: {e}")
            continue

        # Runs a scroll loop over up to 10k points + BM25 indexing (CPU) — push the
        # whole thing off the event loop (#211). A concurrent same-KB rebuild is
        # benign (idempotent: last write wins, both correct).
        await asyncio.to_thread(_ensure_bm25_index, client, kb_id)
        docmap = {d["_id"]: d for d in _hybrid.documents.get(kb_id, [])}
        for r in dense:  # dense-only hits may not be in the scrolled snapshot
            did = r.payload.get("_id", str(r.id))
            docmap.setdefault(
                did,
                {
                    "text": r.payload.get("text", ""),
                    "source": r.payload.get("source", ""),
                    "document_id": r.payload.get("document_id", ""),
                },
            )

        pairs = await _hybrid.hybrid_search(
            kb_id, question_embedding, question, dense, top_k
        )
        for did, score in pairs:
            d = docmap.get(did, {})
            if not _matches_metadata_filter(d, metadata_filter):
                continue  # sparse-only hit from a doc the filter excludes
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


async def retrieve_parent_child(
    pipeline: Dict,
    question: str,
    top_k: int,
    metadata_filter: Optional[MetadataFilter] = None,
) -> Dict:
    """Retrieve child chunks, expand each to its neighbour window (same doc/source)."""
    client = state.get_qdrant_client()
    first_kb_id = pipeline["knowledge_base_ids"][0]
    embed_model = state.knowledge_bases[first_kb_id]["embedding_model"]
    qdrant_filter = build_metadata_filter(metadata_filter)

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
            hits = (
                await asyncio.to_thread(
                    client.query_points,
                    collection_name=kb_id,
                    query=question_embedding,
                    query_filter=qdrant_filter,
                    limit=top_k,
                )
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
                neighbours, _ = await asyncio.to_thread(
                    client.scroll,
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
