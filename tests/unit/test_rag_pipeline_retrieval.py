"""Unit tests for rag-pipeline's core/retrieval.py (#357).

#357: retrieve_hybrid/retrieve_parent_child/_ensure_bm25_index/
invalidate_hybrid_index used to live directly in routes/rag.py (a 688-line
god-module) -- untestable without spinning up full route dependencies.
Extracted into core/retrieval.py, matching graph-rag's routes/api.py (thin) +
core/graph_retriever.py (orchestration) split. These tests prove the
extraction actually achieved its goal: real coverage with fakes, no FastAPI
app needed.

Loaded via sys.path + a stale-cache clear (conftest.py loads every service's
main.py into ONE shared pytest process, so "core"/"models"/"routes" are
already cached as some OTHER service's package) -- matching this session's
established precedent (test_graph_rag_knowledge_graph_handler.py).
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "rag-pipeline"

_COLLISION_PRONE_NAMES = ("core", "routes", "models", "rag", "config", "domain")


def _isolated_import(*module_paths: str):
    """Import all `module_paths` within ONE evict/restore cycle.

    core.state registers Prometheus Counters/Histograms at module level (a
    process-wide global registry) -- calling this helper once per module
    (across separate test files too) would evict+refresh-import core.state
    multiple times, re-registering the same metric names and raising
    DuplicateTimeseries. Every rag-pipeline test needing core.state (directly
    or transitively) must do so via ONE combined call in THIS file -- confirmed
    live: a separate test_rag_pipeline_error_handling.py file doing its own
    fresh import of routes.rag crashed the whole session with exactly this
    error, so those tests were merged in here instead."""
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)

    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


retrieval, rag_routes, system_routes, models = _isolated_import(
    "core.retrieval", "routes.rag", "routes.system", "models"
)


@pytest.fixture(autouse=True)
def _clean_hybrid_cache():
    """_hybrid is a process-local singleton -- reset its cache around each test
    so tests don't leak state into each other."""
    retrieval._hybrid.sparse_index.clear()
    retrieval._hybrid.documents.clear()
    yield
    retrieval._hybrid.sparse_index.clear()
    retrieval._hybrid.documents.clear()


def test_invalidate_hybrid_index_clears_cached_index():
    retrieval._hybrid.sparse_index["kb-1"] = object()
    retrieval._hybrid.documents["kb-1"] = [{"text": "x"}]

    retrieval.invalidate_hybrid_index("kb-1")

    assert "kb-1" not in retrieval._hybrid.sparse_index
    assert "kb-1" not in retrieval._hybrid.documents


def test_invalidate_hybrid_index_is_a_noop_for_unknown_kb():
    retrieval.invalidate_hybrid_index("never-indexed")  # must not raise


@pytest.mark.asyncio
async def test_retrieve_hybrid_raises_503_when_embedding_backend_unavailable(
    monkeypatch,
):
    async def boom(*a, **k):
        raise ConnectionError("ollama unreachable")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: object(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=boom),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    with pytest.raises(Exception) as exc_info:
        await retrieval.retrieve_hybrid(
            {"knowledge_base_ids": ["kb-1"]}, "what is x?", top_k=3
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_retrieve_parent_child_raises_503_when_embedding_backend_unavailable(
    monkeypatch,
):
    async def boom(*a, **k):
        raise ConnectionError("ollama unreachable")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: object(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=boom),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    with pytest.raises(Exception) as exc_info:
        await retrieval.retrieve_parent_child(
            {"knowledge_base_ids": ["kb-1"]}, "what is x?", top_k=3
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_retrieve_parent_child_returns_context_and_sources(monkeypatch):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    hit = _Hit("p1", {"text": "Acme makes widgets.", "source": "doc.txt"}, 0.9)

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            return _QueryResult([hit])

        def scroll(self, **kwargs):
            return [hit], None

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_parent_child(
        {"knowledge_base_ids": ["kb-1"]}, "what does Acme make?", top_k=3
    )

    assert "Acme makes widgets." in result["context"]
    assert result["sources"][0]["source"] == "doc.txt"


# ── Error handling (#357) ───────────────────────────────────────────────────
# create_knowledge_base's Qdrant-collection-creation failure and system.py's
# initialize_ollama failure both used to return HTTPException(500, detail=
# f"...: {str(e)}") -- leaking the raw driver exception string. Switched to
# shared.errors.backend_http_error.


class _KBCreate:
    name = "test-kb"
    description = ""
    embedding_model = "nomic-embed-text"
    llm_model = "llama3.2"
    chunk_size = 512
    chunk_overlap = 50


@pytest.mark.asyncio
async def test_create_knowledge_base_qdrant_failure_does_not_leak_exception_text(
    monkeypatch,
):
    secret_looking = "qdrant://internal-key=hunter2"

    class _BoomClient:
        def create_collection(self, **kwargs):
            raise ConnectionError(secret_looking)

    monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: _BoomClient())
    monkeypatch.setattr(rag_routes.state, "PG_AVAILABLE", False)

    with pytest.raises(Exception) as exc_info:
        await rag_routes.create_knowledge_base(_KBCreate())

    assert exc_info.value.status_code == 503
    assert secret_looking not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_initialize_ollama_failure_does_not_leak_exception_text(monkeypatch):
    secret_looking = "ollama internal token=hunter2"

    async def boom():
        raise ConnectionError(secret_looking)

    monkeypatch.setattr(
        system_routes.state,
        "ollama_manager",
        type("M", (), {"initialize": staticmethod(boom)})(),
    )

    with pytest.raises(Exception) as exc_info:
        await system_routes.initialize_ollama()

    assert exc_info.value.status_code == 503
    assert secret_looking not in str(exc_info.value.detail)


# ── #405: write endpoints must require auth ──────────────────────────────────
# delete_knowledge_base and delete_rag_pipeline had NO application-level auth
# in the route handler itself -- only api-gateway's proxy layer gated writes
# for callers going through it, so a direct network caller (any container on
# minder-network, or host access) could delete either with no credential.
# Reuses this file's already-imported rag_routes (a second, independent
# fresh-import of routes.rag would re-register rag-pipeline's process-global
# Prometheus metrics and crash with DuplicateTimeseries -- confirmed live
# while writing this, matching the warning in _isolated_import's docstring).


def _rag_router_client():
    app = FastAPI()
    app.include_router(rag_routes.router)
    return TestClient(app, raise_server_exceptions=False)


def test_delete_knowledge_base_requires_auth():
    client = _rag_router_client()
    resp = client.delete("/v1/knowledge-bases/kb1")
    assert resp.status_code == 401


def test_delete_rag_pipeline_requires_auth():
    client = _rag_router_client()
    resp = client.delete("/v1/pipeline/p1")
    assert resp.status_code == 401


# ── Metadata filtering (docs/rag-methods.md Bucket 2 -> shipped) ─────────────
# "Qdrant already supports it -- expose filter params on the query endpoint."
# Every retrieval strategy has its own independent Qdrant call (no shared
# repository chokepoint), so each gets its own coverage below -- plus the one
# genuinely tricky case: hybrid's BM25 corpus is cached per-KB and unfiltered,
# so a sparse-only hit from an excluded document must be caught by the
# post-filter, not just the dense side's query_filter.


def test_build_metadata_filter_returns_none_when_nothing_set():
    assert retrieval.build_metadata_filter(None) is None
    assert retrieval.build_metadata_filter(models.MetadataFilter()) is None


def test_build_metadata_filter_ands_both_fields_when_set():
    flt = retrieval.build_metadata_filter(
        models.MetadataFilter(source="doc.txt", document_id="doc-1")
    )
    keys = {c.key for c in flt.must}
    assert keys == {"source", "document_id"}
    values = {c.key: c.match.value for c in flt.must}
    assert values == {"source": "doc.txt", "document_id": "doc-1"}


@pytest.mark.asyncio
async def test_retrieve_relevant_documents_passes_query_filter_to_qdrant(monkeypatch):
    captured = {}

    class _QueryResult:
        points = []

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            captured.update(kwargs)
            return _QueryResult()

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(
        rag_routes.state, "get_qdrant_client", lambda: _FakeQdrantClient()
    )
    monkeypatch.setattr(
        rag_routes.state,
        "knowledge_bases",
        {"kb-1": {"embedding_model": "nomic-embed-text"}},
    )
    monkeypatch.setattr(
        rag_routes.state,
        "ollama_manager",
        SimpleNamespace(generate_embeddings=fake_embed),
    )

    await rag_routes.retrieve_relevant_documents(
        {"knowledge_base_ids": ["kb-1"]},
        "what does Acme make?",
        top_k=3,
        metadata_filter=models.MetadataFilter(source="doc.txt"),
    )

    assert captured["query_filter"] is not None
    assert captured["query_filter"].must[0].key == "source"
    assert captured["query_filter"].must[0].match.value == "doc.txt"


@pytest.mark.asyncio
async def test_retrieve_relevant_documents_no_filter_passes_none(monkeypatch):
    captured = {}

    class _QueryResult:
        points = []

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            captured.update(kwargs)
            return _QueryResult()

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(
        rag_routes.state, "get_qdrant_client", lambda: _FakeQdrantClient()
    )
    monkeypatch.setattr(
        rag_routes.state,
        "knowledge_bases",
        {"kb-1": {"embedding_model": "nomic-embed-text"}},
    )
    monkeypatch.setattr(
        rag_routes.state,
        "ollama_manager",
        SimpleNamespace(generate_embeddings=fake_embed),
    )

    await rag_routes.retrieve_relevant_documents(
        {"knowledge_base_ids": ["kb-1"]}, "what does Acme make?", top_k=3
    )

    assert captured["query_filter"] is None


@pytest.mark.asyncio
async def test_retrieve_parent_child_passes_query_filter_to_qdrant(monkeypatch):
    captured = {}

    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    hit = _Hit("p1", {"text": "Acme makes widgets.", "source": "doc.txt"}, 0.9)

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            captured.update(kwargs)
            return _QueryResult([hit])

        def scroll(self, **kwargs):
            return [hit], None

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    await retrieval.retrieve_parent_child(
        {"knowledge_base_ids": ["kb-1"]},
        "what does Acme make?",
        top_k=3,
        metadata_filter=models.MetadataFilter(document_id="doc-1"),
    )

    assert captured["query_filter"] is not None
    assert captured["query_filter"].must[0].key == "document_id"
    assert captured["query_filter"].must[0].match.value == "doc-1"


@pytest.mark.asyncio
async def test_retrieve_hybrid_excludes_sparse_only_hit_from_excluded_document(
    monkeypatch,
):
    """The tricky case: a document EXCLUDED by metadata_filter still lives in
    the cached, unfiltered BM25 corpus, and BM25 alone can surface it (a
    sparse-only hit with no dense score). Must not appear in the final result —
    proves the post-filter (_matches_metadata_filter), not just the dense
    side's query_filter, is actually doing the work."""

    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    # Only one dense hit, from the ALLOWED document -- the excluded document's
    # chunk is in the BM25 corpus (via scroll) but never among the dense hits.
    allowed_hit = _Hit(
        "allowed-1",
        {
            "_id": "allowed-1",
            "text": "Acme makes widgets.",
            "source": "allowed.txt",
            "document_id": "doc-allowed",
        },
        0.9,
    )
    excluded_point = _Hit(
        "excluded-1",
        {
            "_id": "excluded-1",
            "text": "Globex makes gadgets.",
            "source": "excluded.txt",
            "document_id": "doc-excluded",
        },
        0.0,
    )

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            return _QueryResult([allowed_hit])

        def scroll(self, **kwargs):
            # BM25 corpus covers BOTH documents -- unfiltered, as designed.
            return [allowed_hit, excluded_point], None

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    # Force the excluded document's chunk to win on BM25 alone (a sparse-only
    # hit not present in `dense_scores`) by monkeypatching hybrid_search to
    # return exactly that -- isolates the post-filter from BM25 scoring nuance.
    async def fake_hybrid_search(kb_id, query_embedding, query, dense, top_k):
        return [("allowed-1", 0.5), ("excluded-1", 0.9)]

    monkeypatch.setattr(retrieval._hybrid, "hybrid_search", fake_hybrid_search)

    result = await retrieval.retrieve_hybrid(
        {"knowledge_base_ids": ["kb-1"]},
        "what does Acme make?",
        top_k=5,
        metadata_filter=models.MetadataFilter(document_id="doc-allowed"),
    )

    sources_text = " ".join(s["text"] for s in result["sources"])
    assert "Acme makes widgets." in sources_text
    assert "Globex makes gadgets." not in sources_text
