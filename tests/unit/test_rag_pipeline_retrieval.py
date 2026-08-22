"""Unit tests for rag-pipeline's core/retrieval.py (#357) and core/ingestion.py
(#491) -- both extracted from routes/rag.py for the same reason and merged
into this one file for the same reason (see _isolated_import's docstring
below): a 688-line (then, after #488's metadata_filter, 789-line) god-module,
untestable without spinning up full route dependencies. Extracted matching
graph-rag's routes/api.py (thin) + core/graph_retriever.py (orchestration)
split. These tests prove the extractions actually achieved their goal: real
coverage with fakes, no FastAPI app needed.

Loaded via sys.path + a stale-cache clear (conftest.py loads every service's
main.py into ONE shared pytest process, so "core"/"models"/"routes" are
already cached as some OTHER service's package) -- matching this session's
established precedent (test_graph_rag_knowledge_graph_handler.py).
"""

import contextlib
import functools
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


retrieval, ingestion, rag_routes, system_routes, models = _isolated_import(
    "core.retrieval", "core.ingestion", "routes.rag", "routes.system", "models"
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
        await rag_routes.create_knowledge_base(
            _KBCreate(), current_user={"sub": "alice", "role": "user"}
        )

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


# ── #896/#899: KB delete blocked by dependent pipelines + confirm-to-cascade ──


@pytest.mark.asyncio
async def test_delete_kb_with_no_dependents_succeeds_immediately():
    kb = _kb("kb1")
    with _seed_state(knowledge_bases={"kb1": kb}, rag_pipelines={}, PG_AVAILABLE=False):
        resp = await rag_routes.delete_knowledge_base("kb1", None, {"sub": "1"})
    assert resp == {"message": "Knowledge base deleted", "id": "kb1"}


@pytest.mark.asyncio
async def test_delete_kb_with_dependent_pipeline_without_confirmation_409s():
    kb = _kb("kb1")
    pipe = {"id": "p1", "name": "my-pipe", "knowledge_base_ids": ["kb1"]}
    with _seed_state(
        knowledge_bases={"kb1": kb}, rag_pipelines={"p1": pipe}, PG_AVAILABLE=False
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.delete_knowledge_base("kb1", None, {"sub": "1"})
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["dependent_pipelines"] == [
        {"pipeline_id": "p1", "name": "my-pipe"}
    ]


@pytest.mark.asyncio
async def test_delete_kb_with_stale_confirmation_409s_with_current_list():
    kb = _kb("kb1")
    pipe = {"id": "p1", "name": "my-pipe", "knowledge_base_ids": ["kb1"]}
    with _seed_state(
        knowledge_bases={"kb1": kb}, rag_pipelines={"p1": pipe}, PG_AVAILABLE=False
    ):
        stale_confirm = models.KnowledgeBaseDeleteConfirm(
            confirm_delete_pipeline_ids=["some-other-id"]
        )
        with pytest.raises(Exception) as exc_info:
            await rag_routes.delete_knowledge_base("kb1", stale_confirm, {"sub": "1"})
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["dependent_pipelines"] == [
        {"pipeline_id": "p1", "name": "my-pipe"}
    ]


@pytest.mark.asyncio
async def test_delete_kb_with_exact_confirmation_cascades_and_succeeds():
    kb = _kb("kb1")
    pipe = {"id": "p1", "name": "my-pipe", "knowledge_base_ids": ["kb1"]}
    with _seed_state(
        knowledge_bases={"kb1": kb}, rag_pipelines={"p1": pipe}, PG_AVAILABLE=False
    ):
        confirm = models.KnowledgeBaseDeleteConfirm(confirm_delete_pipeline_ids=["p1"])
        resp = await rag_routes.delete_knowledge_base("kb1", confirm, {"sub": "1"})
        assert resp == {"message": "Knowledge base deleted", "id": "kb1"}
        assert "p1" not in rag_routes.state.rag_pipelines
        assert "kb1" not in rag_routes.state.knowledge_bases


@pytest.mark.asyncio
async def test_query_orphaned_pipeline_returns_clean_error_not_leaked_500():
    """A pipeline whose KB no longer exists (pre-existing orphan, or a race)
    must fail cleanly, not with core/retrieval.py's raw KeyError leaking as a
    500 whose detail is just the missing kb_id string."""
    pipe = {
        "id": "p1",
        "name": "orphan",
        "knowledge_base_ids": ["kb-does-not-exist"],
        "retrieval_config": {},
        "generation_config": {},
    }
    with _seed_state(
        knowledge_bases={}, rag_pipelines={"p1": pipe}, PG_AVAILABLE=False
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.query_rag_pipeline(
                "p1", models.QueryRequest(question="hi"), {"sub": "1"}
            )
    assert exc_info.value.status_code == 409
    assert "kb-does-not-exist" in exc_info.value.detail


# create_knowledge_base/upload_document/create_rag_pipeline/query_rag_pipeline had
# the same gap as delete above: no application-level auth in the handler itself,
# only api-gateway's proxy layer gated them for callers going through it. Unlike
# delete/update (idempotent-ish or metadata-only), these have real cost (Qdrant
# writes, ingest, LLM generation) and can expose knowledge-base content, so a
# direct-network caller had unauthenticated create/upload/query access.


def test_create_knowledge_base_requires_auth():
    client = _rag_router_client()
    resp = client.post(
        "/v1/knowledge-bases",
        json={"name": "kb", "embedding_model": "nomic"},
    )
    assert resp.status_code == 401


def test_upload_document_requires_auth():
    client = _rag_router_client()
    resp = client.post(
        "/v1/knowledge-bases/kb1/upload",
        files={"file": ("doc.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 401


def test_create_rag_pipeline_requires_auth():
    client = _rag_router_client()
    resp = client.post(
        "/v1/pipeline",
        json={"name": "p", "knowledge_base_ids": ["kb1"]},
    )
    assert resp.status_code == 401


def test_query_rag_pipeline_requires_auth():
    client = _rag_router_client()
    resp = client.post("/v1/pipeline/p1/query", json={"question": "hi"})
    assert resp.status_code == 401


# ── PATCH /v1/knowledge-bases/{id}: edit metadata without dropping documents ──
# Previously renaming/re-describing a KB meant delete+recreate, which drops the
# whole Qdrant collection. These prove the in-place metadata update, its auth
# gate, that embedding_model stays immutable, and the 404 path.


def _kb_full(kb_id, **over):
    base = {
        "id": kb_id,
        "name": "old-name",
        "description": "old-desc",
        "embedding_model": "nomic",
        "llm_model": "old-llm",
        "chunk_size": 512,
        "chunk_overlap": 50,
        "document_count": 3,
        "vector_count": 9,
        "created_at": "2026-01-01T00:00:00Z",
    }
    base.update(over)
    return base


def test_update_knowledge_base_requires_auth():
    client = _rag_router_client()
    resp = client.patch("/v1/knowledge-bases/kb1", json={"name": "new"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_kb_changes_mutable_metadata_only():
    kb = _kb_full("kb1")
    with _seed_state(knowledge_bases={"kb1": kb}, PG_AVAILABLE=False):
        resp = await rag_routes.update_knowledge_base(
            "kb1",
            models.KnowledgeBaseUpdate(name="new-name", llm_model="new-llm"),
            {"sub": "1"},
        )
    assert resp.name == "new-name"
    assert resp.llm_model == "new-llm"
    assert resp.description == "old-desc"  # untouched (not in the patch)
    assert resp.embedding_model == "nomic"  # immutable
    assert resp.document_count == 3 and resp.vector_count == 9  # vectors untouched
    assert kb["name"] == "new-name"  # in-memory store mutated in place


@pytest.mark.asyncio
async def test_update_unknown_kb_404():
    with _seed_state(knowledge_bases={}, PG_AVAILABLE=False):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.update_knowledge_base(
                "nope", models.KnowledgeBaseUpdate(name="x"), {"sub": "1"}
            )
    assert exc_info.value.status_code == 404


# ── PATCH /v1/pipeline/{id}: edit a pipeline without delete+recreate ──────────


def test_update_rag_pipeline_requires_auth():
    client = _rag_router_client()
    resp = client.patch("/v1/pipeline/p1", json={"name": "new"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_pipeline_changes_name_and_kbs():
    pipe = {
        "id": "p1",
        "name": "old",
        "knowledge_base_ids": ["kb1"],
        "retrieval_config": {},
        "generation_config": {},
        "created_at": "2026-01-01T00:00:00Z",
    }
    with _seed_state(
        rag_pipelines={"p1": pipe},
        knowledge_bases={"kb1": _kb("kb1"), "kb2": _kb("kb2")},
        PG_AVAILABLE=False,
    ):
        resp = await rag_routes.update_rag_pipeline(
            "p1",
            models.RAGPipelineUpdate(name="renamed", knowledge_base_ids=["kb1", "kb2"]),
            {"sub": "1"},
        )
    assert resp["name"] == "renamed"
    assert resp["knowledge_base_ids"] == ["kb1", "kb2"]


@pytest.mark.asyncio
async def test_update_pipeline_unknown_kb_404():
    pipe = {"id": "p1", "name": "n", "knowledge_base_ids": ["kb1"], "created_at": "x"}
    with _seed_state(
        rag_pipelines={"p1": pipe},
        knowledge_bases={"kb1": _kb("kb1")},
        PG_AVAILABLE=False,
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.update_rag_pipeline(
                "p1",
                models.RAGPipelineUpdate(knowledge_base_ids=["nope"]),
                {"sub": "1"},
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_update_unknown_pipeline_404():
    with _seed_state(rag_pipelines={}, knowledge_bases={}, PG_AVAILABLE=False):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.update_rag_pipeline(
                "nope", models.RAGPipelineUpdate(name="x"), {"sub": "1"}
            )
    assert exc_info.value.status_code == 404


# ── #501: list endpoints return the shared {items,total,limit,offset} envelope ──
# rag-pipeline was the only service whose list endpoints returned a bare JSON
# array (no total/limit/offset), so a client couldn't tell if more pages existed.
# These prove the conversion to shared PaginatedList[T] landed on all three list
# endpoints and that pagination bounds/total are honoured. state.* dicts are the
# process-global stores the endpoints read; snapshot + restore so tests don't leak.


@contextlib.contextmanager
def _seed_state(**dicts):
    saved = {name: getattr(rag_routes.state, name) for name in dicts}
    for name, value in dicts.items():
        setattr(rag_routes.state, name, value)
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(rag_routes.state, name, value)


def _kb(kb_id):
    return {
        "id": kb_id,
        "name": kb_id,
        "description": "d",
        "embedding_model": "e",
        "llm_model": "l",
        "document_count": 0,
        "vector_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
    }


def test_list_knowledge_bases_returns_envelope_with_total():
    client = _rag_router_client()
    kbs = {f"kb{i}": _kb(f"kb{i}") for i in range(5)}
    with _seed_state(knowledge_bases=kbs):
        resp = client.get("/v1/knowledge-bases?limit=2&offset=1")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 5  # pre-slice total, not the page length
    assert body["limit"] == 2
    assert body["offset"] == 1
    assert len(body["items"]) == 2  # sliced to the requested page


def test_list_rag_pipelines_returns_envelope():
    client = _rag_router_client()
    pipes = {
        "p1": {
            "id": "p1",
            "name": "p1",
            "knowledge_base_ids": ["kb1"],
            "created_at": "2026-01-01T00:00:00Z",
        }
    }
    with _seed_state(rag_pipelines=pipes):
        resp = client.get("/v1/pipeline")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 1
    assert body["items"][0]["id"] == "p1"


# ── Metadata filtering (docs/rag-methods.md Bucket 2 -> shipped) ─────────────
# "Qdrant already supports it -- expose filter params on the query endpoint."
# Every retrieval strategy has its own independent Qdrant call (no shared
# repository chokepoint), so each gets its own coverage below -- plus the one
# genuinely tricky case: hybrid's BM25 corpus is cached per-KB and unfiltered,
# so a sparse-only hit from an excluded document must be caught by the
# post-filter, not just the dense side's query_filter.


def test_build_metadata_filter_returns_none_only_with_include_all_levels():
    # #487: by default, "nothing set" still gets the RAPTOR tree_level must_not
    # guard (excludes tree-summary nodes from every non-raptor method) -- None is
    # only returned when there's truly nothing to filter on at all.
    assert retrieval.build_metadata_filter(None) is not None
    assert retrieval.build_metadata_filter(models.MetadataFilter()) is not None
    assert retrieval.build_metadata_filter(None, include_all_levels=True) is None
    assert (
        retrieval.build_metadata_filter(
            models.MetadataFilter(), include_all_levels=True
        )
        is None
    )


def test_build_metadata_filter_excludes_tree_level_above_zero_by_default():
    flt = retrieval.build_metadata_filter(None)
    assert flt.must is None
    assert len(flt.must_not) == 1
    condition = flt.must_not[0]
    assert condition.key == "tree_level"
    assert condition.range.gt == 0


def test_build_metadata_filter_include_all_levels_skips_tree_guard():
    flt = retrieval.build_metadata_filter(
        models.MetadataFilter(source="doc.txt"), include_all_levels=True
    )
    assert flt.must_not is None
    assert {c.key for c in flt.must} == {"source"}


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
async def test_retrieve_relevant_documents_no_filter_still_excludes_tree_nodes(
    monkeypatch,
):
    # #487: with no metadata_filter and include_all_levels defaulting to False,
    # the query_filter is no longer None -- it's the RAPTOR tree_level guard,
    # so every other retrieval method never surfaces LLM-summary nodes.
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

    assert captured["query_filter"] is not None
    assert captured["query_filter"].must is None
    assert captured["query_filter"].must_not[0].key == "tree_level"

    captured.clear()
    await rag_routes.retrieve_relevant_documents(
        {"knowledge_base_ids": ["kb-1"]},
        "what does Acme make?",
        top_k=3,
        include_all_levels=True,
    )
    assert captured["query_filter"] is None


@pytest.mark.asyncio
async def test_retrieve_relevant_documents_raises_503_when_embedding_backend_unavailable(
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
        await retrieval.retrieve_relevant_documents(
            {"knowledge_base_ids": ["kb-1"]}, "what is x?", top_k=3
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_retrieve_relevant_documents_merges_and_sorts_across_multiple_kbs(
    monkeypatch,
):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    class _FakeQdrantClient:
        def __init__(self):
            self.calls = []

        def query_points(self, **kwargs):
            self.calls.append(kwargs["collection_name"])
            if kwargs["collection_name"] == "kb-1":
                return _QueryResult(
                    [_Hit("a", {"text": "low score kb1", "source": "a.txt"}, 0.4)]
                )
            return _QueryResult(
                [_Hit("b", {"text": "high score kb2", "source": "b.txt"}, 0.9)]
            )

    fake_client = _FakeQdrantClient()

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: fake_client,
        knowledge_bases={
            "kb-1": {"embedding_model": "nomic-embed-text"},
            "kb-2": {"embedding_model": "nomic-embed-text"},
        },
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_relevant_documents(
        {"knowledge_base_ids": ["kb-1", "kb-2"]}, "question", top_k=2
    )

    assert fake_client.calls == ["kb-1", "kb-2"]
    # merged across both KBs, sorted by score descending -- kb-2's higher
    # score must come first even though kb-1 was queried first.
    assert result["sources"][0]["text"] == "high score kb2"
    assert result["sources"][1]["text"] == "low score kb1"


@pytest.mark.asyncio
async def test_retrieve_relevant_documents_tolerates_one_kb_failing(monkeypatch):
    """A search failure in one KB must not abort the whole query -- the other
    KB's results should still come back (matching the existing per-KB
    try/except around client.query_points)."""

    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            if kwargs["collection_name"] == "kb-broken":
                raise ConnectionError("qdrant collection missing")
            return _QueryResult([_Hit("a", {"text": "ok", "source": "a.txt"}, 0.5)])

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={
            "kb-broken": {"embedding_model": "nomic-embed-text"},
            "kb-ok": {"embedding_model": "nomic-embed-text"},
        },
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_relevant_documents(
        {"knowledge_base_ids": ["kb-broken", "kb-ok"]}, "question", top_k=5
    )

    assert result["sources"] == [{"text": "ok", "source": "a.txt", "score": 0.5}]


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
    side's query_filter, is actually doing the work.

    Pre-seeds the BM25 cache directly (same trick as
    test_invalidate_hybrid_index_clears_cached_index above) rather than going
    through real indexing, so this stays a true unit test independent of
    rank-bm25 (an optional package, not installed in every CI job).
    """

    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    # Only one dense hit, from the ALLOWED document.
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

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            return _QueryResult([allowed_hit])

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    # "Already indexed" cache covering BOTH documents -- unfiltered, as
    # designed -- so _ensure_bm25_index's `if kb_id in sparse_index: return`
    # short-circuits without touching real rank-bm25.
    retrieval._hybrid.sparse_index["kb-1"] = object()
    retrieval._hybrid.documents["kb-1"] = [
        {
            "_id": "allowed-1",
            "text": "Acme makes widgets.",
            "source": "allowed.txt",
            "document_id": "doc-allowed",
        },
        {
            "_id": "excluded-1",
            "text": "Globex makes gadgets.",
            "source": "excluded.txt",
            "document_id": "doc-excluded",
        },
    ]

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


# ── _ensure_bm25_index (the scroll/pagination loop itself) ─────────────────
# The tests above always pre-seed _hybrid.sparse_index so this scroll loop is
# skipped entirely (avoids depending on the optional rank-bm25 package via
# _hybrid.index_documents). These exercise the loop directly, with
# index_documents monkeypatched to a no-op recorder -- isolating pagination
# from real BM25 indexing.


def test_ensure_bm25_index_paginates_via_scroll_offset_until_none(monkeypatch):
    calls = []

    class _Point:
        def __init__(self, id_, payload):
            self.id = id_
            self.payload = payload

    class _FakeScrollClient:
        def scroll(self, **kwargs):
            calls.append(kwargs.get("offset"))
            if kwargs.get("offset") is None:
                return (
                    [_Point("p1", {"text": "a", "source": "s1", "document_id": "d1"})],
                    "next-page",
                )
            return (
                [_Point("p2", {"text": "b", "source": "s2", "document_id": "d2"})],
                None,
            )

    indexed = {}
    monkeypatch.setattr(
        retrieval._hybrid,
        "index_documents",
        lambda kb_id, docs: indexed.setdefault(kb_id, docs),
    )

    retrieval._ensure_bm25_index(_FakeScrollClient(), "kb-1")

    assert calls == [None, "next-page"]
    assert [d["text"] for d in indexed["kb-1"]] == ["a", "b"]


def test_ensure_bm25_index_skips_indexing_when_no_documents_found(monkeypatch):
    class _FakeScrollClient:
        def scroll(self, **kwargs):
            return [], None

    called = []
    monkeypatch.setattr(
        retrieval._hybrid,
        "index_documents",
        lambda kb_id, docs: called.append((kb_id, docs)),
    )

    retrieval._ensure_bm25_index(_FakeScrollClient(), "kb-empty")

    assert called == []


def test_ensure_bm25_index_short_circuits_when_already_cached():
    retrieval._hybrid.sparse_index["kb-cached"] = object()

    class _BoomClient:
        def scroll(self, **kwargs):
            raise AssertionError("should not scroll when already cached")

    retrieval._ensure_bm25_index(_BoomClient(), "kb-cached")  # must not raise


# ── retrieve_hybrid / retrieve_parent_child: per-KB failure tolerance -------


@pytest.mark.asyncio
async def test_retrieve_hybrid_tolerates_one_kb_failing(monkeypatch):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    ok_hit = _Hit(
        "ok-1",
        {"_id": "ok-1", "text": "ok text", "source": "ok.txt", "document_id": "d1"},
        0.9,
    )

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            if kwargs["collection_name"] == "kb-broken":
                raise RuntimeError("qdrant down")
            return _QueryResult([ok_hit])

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={
            "kb-broken": {"embedding_model": "nomic-embed-text"},
            "kb-ok": {"embedding_model": "nomic-embed-text"},
        },
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    # Pre-seed the BM25 cache for kb-ok so _ensure_bm25_index short-circuits;
    # kb-broken never even reaches that call (query_points raises first).
    retrieval._hybrid.sparse_index["kb-ok"] = object()
    retrieval._hybrid.documents["kb-ok"] = [
        {"_id": "ok-1", "text": "ok text", "source": "ok.txt", "document_id": "d1"}
    ]

    async def fake_hybrid_search(kb_id, query_embedding, query, dense, top_k):
        return [("ok-1", 0.9)]

    monkeypatch.setattr(retrieval._hybrid, "hybrid_search", fake_hybrid_search)

    result = await retrieval.retrieve_hybrid(
        {"knowledge_base_ids": ["kb-broken", "kb-ok"]}, "question", top_k=5
    )

    assert result["sources"] == [{"text": "ok text", "source": "ok.txt", "score": 0.9}]


@pytest.mark.asyncio
async def test_retrieve_parent_child_tolerates_one_kb_failing(monkeypatch):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    ok_hit = _Hit("ok-1", {"text": "ok text", "source": "ok.txt"}, 0.9)

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            if kwargs["collection_name"] == "kb-broken":
                raise RuntimeError("qdrant down")
            return _QueryResult([ok_hit])

        def scroll(self, **kwargs):
            return [ok_hit], None

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={
            "kb-broken": {"embedding_model": "nomic-embed-text"},
            "kb-ok": {"embedding_model": "nomic-embed-text"},
        },
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_parent_child(
        {"knowledge_base_ids": ["kb-broken", "kb-ok"]}, "question", top_k=5
    )

    assert [s["text"] for s in result["sources"]] == ["ok text"]


# ── retrieve_parent_child: the actual neighbour-window expansion path -------
# The tests above only ever hit older chunks with no chunk_index (the
# leave-as-is branch) -- these cover the real small-to-big expansion.


@pytest.mark.asyncio
async def test_retrieve_parent_child_expands_to_neighbour_window(monkeypatch):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    center_hit = _Hit(
        "child-2",
        {"text": "middle chunk.", "source": "doc.txt", "chunk_index": 2},
        0.9,
    )
    # Neighbour window comes back out of order -- must be re-sorted by chunk_index.
    neighbours = [
        _Hit(
            "child-3",
            {"text": "last chunk.", "source": "doc.txt", "chunk_index": 3},
            0.5,
        ),
        _Hit(
            "child-1",
            {"text": "first chunk.", "source": "doc.txt", "chunk_index": 1},
            0.5,
        ),
        center_hit,
    ]

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            return _QueryResult([center_hit])

        def scroll(self, **kwargs):
            return neighbours, None

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_parent_child(
        {"knowledge_base_ids": ["kb-1"]}, "question", top_k=3
    )

    assert result["sources"][0]["text"] == "first chunk.\nmiddle chunk.\nlast chunk."
    assert result["sources"][0]["context_type"] == "parent"
    assert result["sources"][0]["child_chunk_index"] == 2


@pytest.mark.asyncio
async def test_retrieve_parent_child_dedupes_hits_sharing_the_same_window(monkeypatch):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    # Two dense hits land in the SAME (source, chunk_index) window -- only the
    # first should trigger a neighbour fetch / produce a source entry.
    hit_a = _Hit(
        "child-2a", {"text": "chunk a", "source": "doc.txt", "chunk_index": 2}, 0.9
    )
    hit_b = _Hit(
        "child-2b", {"text": "chunk b", "source": "doc.txt", "chunk_index": 2}, 0.8
    )

    scroll_calls = []

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            return _QueryResult([hit_a, hit_b])

        def scroll(self, **kwargs):
            scroll_calls.append(kwargs)
            return [hit_a], None

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_parent_child(
        {"knowledge_base_ids": ["kb-1"]}, "question", top_k=3
    )

    assert len(scroll_calls) == 1  # deduped -- only one neighbour fetch
    assert len(result["sources"]) == 1


@pytest.mark.asyncio
async def test_retrieve_parent_child_falls_back_to_the_hit_when_neighbour_fetch_fails(
    monkeypatch,
):
    class _Hit:
        def __init__(self, id_, payload, score):
            self.id = id_
            self.payload = payload
            self.score = score

    class _QueryResult:
        def __init__(self, points):
            self.points = points

    hit = _Hit(
        "child-2", {"text": "solo chunk.", "source": "doc.txt", "chunk_index": 2}, 0.9
    )

    class _FakeQdrantClient:
        def query_points(self, **kwargs):
            return _QueryResult([hit])

        def scroll(self, **kwargs):
            raise RuntimeError("qdrant scroll timed out")

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3]]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        knowledge_bases={"kb-1": {"embedding_model": "nomic-embed-text"}},
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
    )
    monkeypatch.setattr(retrieval, "state", fake_state)

    result = await retrieval.retrieve_parent_child(
        {"knowledge_base_ids": ["kb-1"]}, "question", top_k=3
    )

    # Neighbour scroll failed -- falls back to just the original hit's own text.
    assert result["sources"][0]["text"] == "solo chunk."


# ── _matches_metadata_filter: no-filter passthrough --------------------------


def test_matches_metadata_filter_returns_true_when_filter_is_none():
    assert retrieval._matches_metadata_filter({"source": "anything"}, None) is True


def test_matches_metadata_filter_rejects_a_source_mismatch():
    doc = {"source": "wrong.txt", "document_id": "d1"}
    assert (
        retrieval._matches_metadata_filter(
            doc, models.MetadataFilter(source="right.txt")
        )
        is False
    )


# ── Document ingestion (core/ingestion.py, #491) ────────────────────────────
# upload_document/_group_documents had ZERO unit coverage before this
# extraction -- only integration tests (needing the full stack running)
# exercised them. These fakes prove the same thing #357's tests proved for
# retrieval: real coverage, no FastAPI app or live Qdrant/Ollama needed.


class _FakeMetric:
    """Stand-in for a Prometheus Counter/Histogram: .labels(...) returns self,
    .inc() is a no-op, .time() is a no-op context manager."""

    def labels(self, **kwargs):
        return self

    def inc(self):
        pass

    def time(self):
        return contextlib.nullcontext()


def _fake_kb(**overrides):
    kb = {
        "chunk_size": 512,
        "chunk_overlap": 50,
        "embedding_model": "nomic-embed-text",
        "document_count": 0,
        "vector_count": 0,
    }
    kb.update(overrides)
    return kb


def _fake_chunk_text(text, chunk_size=512, chunk_overlap=50):
    """Stand-in for the real chunk_text: langchain-text-splitters is an
    optional per-service dependency (rag-pipeline's own requirements.txt),
    not installed in CI's plain "Unit Tests" job (root requirements.txt
    only) -- same class of gap as the rank-bm25 one fixed earlier this
    session. One chunk per non-empty text is enough to exercise
    ingest_document's own logic; the real splitter's behavior is covered by
    its own dedicated tests, not re-tested here."""
    return [text] if text.strip() else []


@pytest.mark.asyncio
async def test_ingest_document_raises_400_when_no_text_extracted(monkeypatch):
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)

    with pytest.raises(Exception) as exc_info:
        await ingestion.ingest_document("kb-1", _fake_kb(), "empty.txt", b"")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_ingest_document_raises_415_for_unsupported_binary_content(monkeypatch):
    """#900: a real PNG (or any content matching no registered extractor)
    must be cleanly rejected at ingest time, not silently latin-1-decoded
    into garbage and embedded."""
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    with pytest.raises(Exception) as exc_info:
        await ingestion.ingest_document("kb-1", _fake_kb(), "image.png", png_bytes)
    assert exc_info.value.status_code == 415


@pytest.mark.asyncio
async def test_ingest_document_raises_503_when_embedding_backend_unavailable(
    monkeypatch,
):
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)

    async def boom(texts, model):
        raise ConnectionError("ollama unreachable")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: object(),
        ollama_manager=SimpleNamespace(generate_embeddings=boom),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    with pytest.raises(Exception) as exc_info:
        await ingestion.ingest_document(
            "kb-1", _fake_kb(), "doc.txt", b"Some real document text."
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_ingest_document_stores_chunks_and_updates_kb_stats(monkeypatch):
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)
    captured = {}

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            captured.update(kwargs)

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    kb = _fake_kb()
    result = await ingestion.ingest_document(
        "kb-1", kb, "doc.txt", b"Acme makes widgets."
    )

    assert result.filename == "doc.txt"
    assert result.chunks_processed >= 1
    assert result.vectors_created == result.chunks_processed
    assert result.document_id

    assert captured["collection_name"] == "kb-1"
    assert len(captured["points"]) == result.chunks_processed
    assert captured["points"][0].payload["source"] == "doc.txt"
    assert captured["points"][0].payload["document_id"] == result.document_id

    # KB stats updated in place (the same dict callers hold onto).
    assert kb["document_count"] == 1
    assert kb["vector_count"] == result.chunks_processed


@pytest.mark.asyncio
async def test_ingest_document_invalidates_hybrid_cache(monkeypatch):
    """Proves invalidate_hybrid_index is actually called, not just imported --
    a stale cache would let a hybrid query miss the newly-uploaded chunks."""
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            pass

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    retrieval._hybrid.sparse_index["kb-1"] = object()
    retrieval._hybrid.documents["kb-1"] = [{"text": "stale"}]

    await ingestion.ingest_document("kb-1", _fake_kb(), "doc.txt", b"New content.")

    assert "kb-1" not in retrieval._hybrid.sparse_index
    assert "kb-1" not in retrieval._hybrid.documents


@pytest.mark.asyncio
async def test_ingest_document_cleanup_failure_is_logged_not_raised_over(monkeypatch):
    """The delete-cleanup itself can ALSO fail (Qdrant still unreachable) --
    must still surface the original 503, not crash inside the except block."""
    chunk_count = ingestion.QDRANT_UPSERT_BATCH_SIZE + 10
    monkeypatch.setattr(
        ingestion,
        "chunk_text",
        lambda *a, **k: [f"chunk {i}" for i in range(chunk_count)],
    )

    class _DoublyFlakyQdrantClient:
        def upsert(self, **kwargs):
            raise ConnectionError("qdrant unreachable")

        def delete(self, **kwargs):
            raise ConnectionError("qdrant still unreachable")

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _DoublyFlakyQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    with pytest.raises(Exception) as exc_info:
        await ingestion.ingest_document(
            "kb-1", _fake_kb(), "big.txt", b"doesn't matter, chunk_text is stubbed"
        )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_ingest_document_saves_kb_to_postgres_when_available(monkeypatch):
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)
    saved = {}

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            pass

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def fake_save(kb_id, kb):
        saved["kb_id"] = kb_id

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=True,
        save_kb_to_postgres=fake_save,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    await ingestion.ingest_document("kb-1", _fake_kb(), "doc.txt", b"New content.")

    assert saved["kb_id"] == "kb-1"


@pytest.mark.asyncio
async def test_ingest_document_tolerates_postgres_save_failure(monkeypatch):
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            pass

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    async def failing_save(kb_id, kb):
        raise ConnectionError("postgres unreachable")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=True,
        save_kb_to_postgres=failing_save,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    # Must still succeed overall -- the vectors are already safely in Qdrant.
    result = await ingestion.ingest_document(
        "kb-1", _fake_kb(), "doc.txt", b"New content."
    )
    assert result.filename == "doc.txt"


# ── _build_and_store_tree / ingest_document(build_tree=True) ----------------


@pytest.mark.asyncio
async def test_build_and_store_tree_upserts_summary_nodes(monkeypatch):
    async def fake_generate_response(prompt, model):
        return {"text": "a concise summary"}

    async def fake_generate_embeddings(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        ollama_manager=SimpleNamespace(
            generate_response=fake_generate_response,
            generate_embeddings=fake_generate_embeddings,
        ),
        get_qdrant_client=lambda: _UpsertCapturingClient(),
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    leaf_ids = [f"leaf-{i}" for i in range(6)]
    leaf_texts = [f"chunk {i} content" for i in range(6)]
    leaf_embeddings = [[0.1, 0.2, 0.3] for _ in range(6)]

    node_count = await ingestion._build_and_store_tree(
        "kb-1",
        _fake_kb(llm_model="llama3.2"),
        "doc-1",
        "doc.txt",
        "2026-01-01T00:00:00+00:00",
        leaf_ids,
        leaf_texts,
        leaf_embeddings,
    )

    assert node_count > 0
    assert _UpsertCapturingClient.last_points
    assert _UpsertCapturingClient.last_points[0].payload["document_id"] == "doc-1"
    assert _UpsertCapturingClient.last_points[0].payload["tree_level"] >= 1


class _UpsertCapturingClient:
    last_points: list = []

    def upsert(self, **kwargs):
        type(self).last_points = kwargs["points"]


@pytest.mark.asyncio
async def test_build_and_store_tree_summary_falls_back_when_llm_reports_error(
    monkeypatch,
):
    """summarize()'s own error-branch (a generate_response() error envelope,
    not an exception) -- exercised via the REAL raptor.build_tree rather than
    a fake, since raptor itself degrades an empty summary to a truncated
    concatenation of the cluster's text (never drops the cluster)."""

    async def erroring_generate_response(prompt, model):
        return {"error": True, "text": "model unavailable"}

    async def fake_generate_embeddings(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        ollama_manager=SimpleNamespace(
            generate_response=erroring_generate_response,
            generate_embeddings=fake_generate_embeddings,
        ),
        get_qdrant_client=lambda: _UpsertCapturingClient(),
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    leaf_ids = [f"leaf-{i}" for i in range(6)]
    leaf_texts = [f"distinct chunk number {i} about topic {i}" for i in range(6)]
    leaf_embeddings = [
        [float(i), float(i) * 2, float(i) * 3] for i in range(6)
    ]  # spread out so clustering actually reduces the node count

    node_count = await ingestion._build_and_store_tree(
        "kb-1",
        _fake_kb(llm_model="llama3.2"),
        "doc-1",
        "doc.txt",
        "2026-01-01T00:00:00+00:00",
        leaf_ids,
        leaf_texts,
        leaf_embeddings,
    )

    assert node_count > 0
    # No exception propagated, and a real (non-empty) node was still produced --
    # raptor.build_tree's own fallback truncated the cluster's own text instead.
    text = _UpsertCapturingClient.last_points[0].payload["text"]
    assert text  # non-empty fallback text, not a blank summary


@pytest.mark.asyncio
async def test_build_and_store_tree_returns_zero_when_raptor_raises(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("clustering failed")

    monkeypatch.setattr(ingestion.raptor, "build_tree", boom)

    node_count = await ingestion._build_and_store_tree(
        "kb-1", _fake_kb(), "doc-1", "doc.txt", "2026-01-01T00:00:00+00:00", [], [], []
    )

    assert node_count == 0


@pytest.mark.asyncio
async def test_build_and_store_tree_returns_zero_when_no_nodes_produced(monkeypatch):
    async def empty_tree(*args, **kwargs):
        return []

    monkeypatch.setattr(ingestion.raptor, "build_tree", empty_tree)

    node_count = await ingestion._build_and_store_tree(
        "kb-1", _fake_kb(), "doc-1", "doc.txt", "2026-01-01T00:00:00+00:00", [], [], []
    )

    assert node_count == 0


@pytest.mark.asyncio
async def test_ingest_document_builds_tree_when_requested_and_within_chunk_bounds(
    monkeypatch,
):
    chunk_count = ingestion.raptor.MIN_CHUNKS_FOR_TREE
    monkeypatch.setattr(
        ingestion,
        "chunk_text",
        lambda *a, **k: [f"chunk {i} content" for i in range(chunk_count)],
    )

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            pass

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    tree_calls = []

    async def fake_build_and_store_tree(*args, **kwargs):
        tree_calls.append(args)
        return 3

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)
    monkeypatch.setattr(ingestion, "_build_and_store_tree", fake_build_and_store_tree)

    result = await ingestion.ingest_document(
        "kb-1", _fake_kb(), "big.txt", b"doesn't matter", build_tree=True
    )

    assert len(tree_calls) == 1
    assert result.tree_nodes_created == 3


@pytest.mark.asyncio
async def test_ingest_document_skips_tree_when_too_few_chunks(monkeypatch):
    monkeypatch.setattr(ingestion, "chunk_text", _fake_chunk_text)  # always 1 chunk

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            pass

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    def _boom(*args, **kwargs):
        raise AssertionError("tree build must be skipped below MIN_CHUNKS_FOR_TREE")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)
    monkeypatch.setattr(ingestion, "_build_and_store_tree", _boom)

    result = await ingestion.ingest_document(
        "kb-1", _fake_kb(), "doc.txt", b"short doc", build_tree=True
    )

    assert result.tree_nodes_created == 0


@pytest.mark.asyncio
async def test_list_documents_requests_tree_level_in_payload(monkeypatch):
    """list_documents must scroll WITH tree_level so group_documents can exclude
    RAPTOR tree-summary nodes; without it tree nodes inflate chunk_count (#694)."""
    captured = {}

    class _FakeQdrantClient:
        def scroll(self, **kwargs):
            captured.update(kwargs)
            return [], None

    fake_state = SimpleNamespace(
        knowledge_bases={"kb-1": {}},
        get_qdrant_client=lambda: _FakeQdrantClient(),
    )
    monkeypatch.setattr(rag_routes, "state", fake_state)

    await rag_routes.list_documents("kb-1")

    assert "tree_level" in captured["with_payload"]


@pytest.mark.asyncio
async def test_ingest_document_upserts_in_batches_above_the_batch_size(monkeypatch):
    """#683: a document with more chunks than QDRANT_UPSERT_BATCH_SIZE must be
    upserted across multiple requests, not one giant one -- mirrors the
    embedding phase's own EMBED_BATCH_SIZE batching."""
    chunk_count = ingestion.QDRANT_UPSERT_BATCH_SIZE + 10
    monkeypatch.setattr(
        ingestion,
        "chunk_text",
        lambda *a, **k: [f"chunk {i}" for i in range(chunk_count)],
    )

    calls = []

    class _FakeQdrantClient:
        def upsert(self, **kwargs):
            calls.append(kwargs)

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    result = await ingestion.ingest_document(
        "kb-1", _fake_kb(), "big.txt", b"doesn't matter, chunk_text is stubbed"
    )

    assert len(calls) == 2  # 96 + 10, split across two batches
    assert len(calls[0]["points"]) == ingestion.QDRANT_UPSERT_BATCH_SIZE
    assert len(calls[1]["points"]) == 10
    assert result.chunks_processed == chunk_count


@pytest.mark.asyncio
async def test_ingest_document_cleans_up_partial_write_on_upsert_failure(monkeypatch):
    """#683: if a later batch fails, delete whatever THIS upload already wrote
    (by document_id) so the upload still fails atomically overall instead of
    leaving a half-indexed document behind."""
    chunk_count = ingestion.QDRANT_UPSERT_BATCH_SIZE + 10
    monkeypatch.setattr(
        ingestion,
        "chunk_text",
        lambda *a, **k: [f"chunk {i}" for i in range(chunk_count)],
    )

    upsert_calls = []
    delete_calls = []

    class _FlakyQdrantClient:
        def upsert(self, **kwargs):
            upsert_calls.append(kwargs)
            if len(upsert_calls) == 2:
                raise ConnectionError("qdrant unreachable")

        def delete(self, **kwargs):
            delete_calls.append(kwargs)

    async def fake_embed(texts, model):
        return [[0.1, 0.2, 0.3] for _ in texts]

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FlakyQdrantClient(),
        ollama_manager=SimpleNamespace(generate_embeddings=fake_embed),
        embedding_generation_duration=_FakeMetric(),
        documents_processed_total=_FakeMetric(),
        PG_AVAILABLE=False,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    with pytest.raises(Exception) as exc_info:
        await ingestion.ingest_document(
            "kb-1", _fake_kb(), "big.txt", b"doesn't matter, chunk_text is stubbed"
        )
    assert exc_info.value.status_code == 503

    assert len(upsert_calls) == 2  # first batch succeeded, second raised
    assert len(delete_calls) == 1
    condition = delete_calls[0]["points_selector"].must[0]
    assert condition.key == "document_id"
    assert condition.match.value  # a document_id was generated and used


def test_group_documents_groups_by_document_id():
    class _Record:
        def __init__(self, payload):
            self.payload = payload

    records = [
        _Record({"source": "a.txt", "document_id": "doc-1", "uploaded_at": "t1"}),
        _Record({"source": "a.txt", "document_id": "doc-1", "uploaded_at": "t1"}),
        _Record({"source": "b.txt", "document_id": "doc-2", "uploaded_at": "t2"}),
    ]

    result = {d.document_id: d for d in ingestion.group_documents(records)}

    assert result["doc-1"].filename == "a.txt"
    assert result["doc-1"].chunk_count == 2
    assert result["doc-2"].filename == "b.txt"
    assert result["doc-2"].chunk_count == 1


def test_group_documents_falls_back_to_legacy_source_grouping():
    """Points from before document_id existed have no document_id in their
    payload at all -- grouped by filename instead, with a synthetic
    legacy:<filename> id (the finest granularity available for that data)."""

    class _Record:
        def __init__(self, payload):
            self.payload = payload

    records = [
        _Record({"source": "old.txt"}),
        _Record({"source": "old.txt"}),
    ]

    result = ingestion.group_documents(records)

    assert len(result) == 1
    assert result[0].document_id == "legacy:old.txt"
    assert result[0].chunk_count == 2


# ── Upload size limit (routes/rag.py's upload_document) ────────────────────
# Previously unenforced anywhere in the platform: an upload of any size was
# fully buffered into memory with no limit -- a real risk on the Pi-class
# hardware this deploys to. These prove the bounded-read rejects an oversized
# file before it ever reaches ingest_document, and passes a within-limit file
# through unchanged.


class _FakeUploadFile:
    def __init__(self, data: bytes, filename: str = "doc.txt"):
        self._data = data
        self.filename = filename

    async def read(self, size=None):
        if size is None:
            return self._data
        return self._data[:size]


@pytest.mark.asyncio
async def test_upload_document_rejects_file_over_the_configured_limit(monkeypatch):
    monkeypatch.setattr(rag_routes.settings, "MAX_UPLOAD_SIZE_MB", 0)
    monkeypatch.setattr(rag_routes.state, "knowledge_bases", {"kb-1": _fake_kb()})
    called = {"ingest": False}

    async def fake_ingest(*a, **k):
        called["ingest"] = True

    monkeypatch.setattr(rag_routes, "ingest_document", fake_ingest)

    with pytest.raises(Exception) as exc_info:
        await rag_routes.upload_document(
            kb_id="kb-1", file=_FakeUploadFile(b"way more than one byte")
        )

    assert exc_info.value.status_code == 413
    assert called["ingest"] is False  # rejected before ever reaching ingestion


@pytest.mark.asyncio
async def test_upload_document_passes_within_limit_file_through(monkeypatch):
    monkeypatch.setattr(rag_routes.settings, "MAX_UPLOAD_SIZE_MB", 1)
    kb = _fake_kb()
    monkeypatch.setattr(rag_routes.state, "knowledge_bases", {"kb-1": kb})
    captured = {}

    async def fake_ingest(kb_id, kb_arg, filename, content, build_tree=False):
        captured.update(
            kb_id=kb_id, filename=filename, content=content, build_tree=build_tree
        )
        return "ok"

    monkeypatch.setattr(rag_routes, "ingest_document", fake_ingest)

    result = await rag_routes.upload_document(
        kb_id="kb-1",
        file=_FakeUploadFile(b"small document", filename="doc.txt"),
        build_tree=False,
    )

    assert result == "ok"
    assert captured == {
        "kb_id": "kb-1",
        "filename": "doc.txt",
        "content": b"small document",
        "build_tree": False,
    }


# ── KB count reconciliation vs Qdrant (#629) ───────────────────────────────
# On a best-effort Postgres save failure the in-memory counts still bumped but
# Postgres kept the old value; after a restart the stale Postgres row won, so a
# KB's reported document_count/vector_count silently reverted below what's really
# in Qdrant. reconcile_kb_counts_from_qdrant heals that on startup, counting leaf
# chunks only (RAPTOR tree-summary nodes excluded, matching vector_count's meaning).


class _FakeScrollClient:
    """Returns all records in one scroll batch (next_offset -> None). `raises`
    simulates a KB whose Qdrant collection was never created (nothing uploaded)."""

    def __init__(self, records, raises=False):
        self._records = records
        self._raises = raises

    def scroll(self, **kwargs):
        if self._raises:
            raise RuntimeError("collection not found")
        return list(self._records), None


def _pt(document_id, tree_level=0, source="doc.txt"):
    return SimpleNamespace(
        payload={
            "document_id": document_id,
            "tree_level": tree_level,
            "source": source,
        }
    )


def _fake_state(records, saves, pg_available=True, raises=False):
    async def save_kb_to_postgres(kb_id, kb):
        saves.append((kb_id, dict(kb)))

    return SimpleNamespace(
        get_qdrant_client=lambda: _FakeScrollClient(records, raises=raises),
        PG_AVAILABLE=pg_available,
        save_kb_to_postgres=save_kb_to_postgres,
    )


@pytest.mark.asyncio
async def test_reconcile_corrects_drift_and_persists(monkeypatch):
    # Qdrant has 3 leaf chunks for one document (+1 tree node that must NOT count).
    records = [_pt("d1"), _pt("d1"), _pt("d1"), _pt("d1", tree_level=1)]
    saves = []
    monkeypatch.setattr(ingestion, "state", _fake_state(records, saves))

    kbs = {"kb-1": {"document_count": 0, "vector_count": 0}}
    fixed = await ingestion.reconcile_kb_counts_from_qdrant(kbs)

    assert fixed == 1
    assert kbs["kb-1"]["document_count"] == 1
    assert kbs["kb-1"]["vector_count"] == 3  # tree node excluded
    assert saves == [("kb-1", {"document_count": 1, "vector_count": 3})]


@pytest.mark.asyncio
async def test_reconcile_noop_when_counts_already_match(monkeypatch):
    records = [_pt("d1"), _pt("d1"), _pt("d1")]
    saves = []
    monkeypatch.setattr(ingestion, "state", _fake_state(records, saves))

    kbs = {"kb-1": {"document_count": 1, "vector_count": 3}}
    fixed = await ingestion.reconcile_kb_counts_from_qdrant(kbs)

    assert fixed == 0
    assert saves == []  # no write when nothing drifted


@pytest.mark.asyncio
async def test_reconcile_skips_kb_with_missing_collection(monkeypatch):
    saves = []
    monkeypatch.setattr(ingestion, "state", _fake_state([], saves, raises=True))

    kbs = {"kb-1": {"document_count": 5, "vector_count": 42}}
    fixed = await ingestion.reconcile_kb_counts_from_qdrant(kbs)

    assert fixed == 0
    assert kbs["kb-1"] == {"document_count": 5, "vector_count": 42}  # untouched
    assert saves == []


@pytest.mark.asyncio
async def test_reconcile_does_not_persist_when_pg_unavailable(monkeypatch):
    records = [_pt("d1"), _pt("d1")]
    saves = []
    monkeypatch.setattr(
        ingestion, "state", _fake_state(records, saves, pg_available=False)
    )

    kbs = {"kb-1": {"document_count": 0, "vector_count": 0}}
    fixed = await ingestion.reconcile_kb_counts_from_qdrant(kbs)

    assert fixed == 1  # in-memory corrected...
    assert kbs["kb-1"]["vector_count"] == 2
    assert saves == []  # ...but no Postgres write attempted


@pytest.mark.asyncio
async def test_reconcile_tolerates_postgres_persist_failure(monkeypatch):
    records = [_pt("d1"), _pt("d1")]

    async def failing_save(kb_id, kb):
        raise ConnectionError("postgres unreachable")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: _FakeScrollClient(records),
        PG_AVAILABLE=True,
        save_kb_to_postgres=failing_save,
    )
    monkeypatch.setattr(ingestion, "state", fake_state)

    kbs = {"kb-1": {"document_count": 0, "vector_count": 0}}
    fixed = await ingestion.reconcile_kb_counts_from_qdrant(kbs)

    # In-memory correction still applied and reported despite the failed
    # persist -- Qdrant is the source of truth, Postgres is best-effort.
    assert fixed == 1
    assert kbs["kb-1"]["vector_count"] == 2


# ── GET .../documents/{document_id}/chunks ────────────────────────────────────
# Lets a caller inspect what actually got extracted/stored for a document (a
# diagnostic step separate from a retrieval/generation issue) -- previously
# nothing exposed chunk text at all, only per-document summaries.


class _FakeChunkRecord:
    def __init__(self, payload):
        self.payload = payload


class _FakeChunksQdrantClient:
    def __init__(self, records):
        self._records = records
        self.scroll_calls = []

    def scroll(self, **kwargs):
        self.scroll_calls.append(kwargs)
        return self._records, None


@pytest.mark.asyncio
async def test_get_document_chunks_returns_sorted_chunks_excluding_tree_nodes(
    monkeypatch,
):
    records = [
        _FakeChunkRecord({"chunk_index": 2, "text": "third"}),
        _FakeChunkRecord({"chunk_index": 0, "text": "first"}),
        _FakeChunkRecord({"chunk_index": 1, "text": "second"}),
        _FakeChunkRecord({"chunk_index": 0, "text": "tree summary", "tree_level": 1}),
    ]
    fake_client = _FakeChunksQdrantClient(records)
    with _seed_state(knowledge_bases={"kb-1": _kb("kb-1")}):
        monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
        # Explicit limit/offset: called directly (not through FastAPI's request
        # handling), so the function's own Query(...) defaults would otherwise
        # arrive as unresolved Query sentinel objects, not plain ints.
        result = await rag_routes.get_document_chunks(
            "kb-1", "doc-1", limit=50, offset=0
        )

    assert [c.text for c in result.items] == ["first", "second", "third"]
    assert [c.chunk_index for c in result.items] == [0, 1, 2]
    assert result.total == 3  # tree-summary node excluded from the count too


@pytest.mark.asyncio
async def test_get_document_chunks_404_for_unknown_kb():
    with _seed_state(knowledge_bases={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.get_document_chunks("nope", "doc-1")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_document_chunks_404_when_document_has_no_chunks(monkeypatch):
    fake_client = _FakeChunksQdrantClient([])
    with _seed_state(knowledge_bases={"kb-1": _kb("kb-1")}):
        monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
        with pytest.raises(Exception) as exc_info:
            await rag_routes.get_document_chunks("kb-1", "nope")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_document_chunks_paginates_via_limit_offset(monkeypatch):
    records = [
        _FakeChunkRecord({"chunk_index": i, "text": f"chunk {i}"}) for i in range(5)
    ]
    fake_client = _FakeChunksQdrantClient(records)
    with _seed_state(knowledge_bases={"kb-1": _kb("kb-1")}):
        monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
        result = await rag_routes.get_document_chunks(
            "kb-1", "doc-1", limit=2, offset=2
        )

    assert result.total == 5
    assert result.limit == 2
    assert result.offset == 2
    assert [c.chunk_index for c in result.items] == [2, 3]


@pytest.mark.asyncio
async def test_get_document_chunks_scopes_to_the_requested_document(monkeypatch):
    """Confirms the shared _document_id_filter is actually applied to the
    scroll call, not just built and ignored."""
    fake_client = _FakeChunksQdrantClient(
        [_FakeChunkRecord({"chunk_index": 0, "text": "x"})]
    )
    with _seed_state(knowledge_bases={"kb-1": _kb("kb-1")}):
        monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
        await rag_routes.get_document_chunks(
            "kb-1", "legacy:notes.txt", limit=50, offset=0
        )

    scroll_filter = fake_client.scroll_calls[0]["scroll_filter"]
    assert scroll_filter == rag_routes._document_id_filter("legacy:notes.txt")


def test_get_document_chunks_route_is_wired_and_open_read(monkeypatch):
    """Through the real router (not a direct call) -- proves the route path
    itself resolves and the Query(...) limit/offset defaults actually work
    when FastAPI, not a test, supplies them."""
    fake_client = _FakeChunksQdrantClient(
        [_FakeChunkRecord({"chunk_index": 0, "text": "hello"})]
    )
    client = _rag_router_client()
    with _seed_state(knowledge_bases={"kb-1": _kb("kb-1")}):
        monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
        resp = client.get("/v1/knowledge-bases/kb-1/documents/doc-1/chunks")

    assert resp.status_code == 200  # no auth required -- matches list_documents
    body = resp.json()
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["items"] == [{"chunk_index": 0, "text": "hello"}]


# ── delete_document: legacy delete must not sweep up a document_id-tagged
# re-upload sharing the same filename ────────────────────────────────────────


class _FakeCountResult:
    def __init__(self, count):
        self.count = count


class _FakeDeleteQdrantClient:
    """Captures the Filter passed to count()/delete() so the test can assert
    on its exact structure (must include an IsEmptyCondition on document_id
    for a legacy: delete, not just a bare source match)."""

    def __init__(self, count=1):
        self._count = count
        self.count_filters = []
        self.delete_filters = []

    def count(self, collection_name, count_filter):
        self.count_filters.append(count_filter)
        return _FakeCountResult(self._count)

    def delete(self, collection_name, points_selector):
        self.delete_filters.append(points_selector)


@pytest.mark.asyncio
async def test_legacy_delete_filter_excludes_document_id_tagged_chunks(monkeypatch):
    """Found in a background audit: a legacy:<filename> delete used to filter
    on `source` alone, with no exclusion for chunks that DO carry a
    document_id -- so deleting an old pre-#427 upload's legacy entry would
    silently also delete a LATER, still-wanted re-upload of the same filename
    (which gets its own fresh document_id, per #427's whole point). The fix
    adds an IsEmptyCondition on document_id to both the count and delete
    filters, scoping a legacy delete to strictly the no-document_id chunks."""
    from qdrant_client.models import IsEmptyCondition

    fake_client = _FakeDeleteQdrantClient(count=3)
    kb = _fake_kb()
    monkeypatch.setattr(rag_routes.state, "knowledge_bases", {"kb-1": kb})
    monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
    monkeypatch.setattr(rag_routes.state, "PG_AVAILABLE", False)
    monkeypatch.setattr(rag_routes, "invalidate_hybrid_index", lambda kb_id: None)

    await rag_routes.delete_document(
        kb_id="kb-1", document_id="legacy:notes.txt", current_user={"sub": "u1"}
    )

    for filter_ in (fake_client.count_filters[0], fake_client.delete_filters[0]):
        assert any(
            isinstance(cond, IsEmptyCondition) and cond.is_empty.key == "document_id"
            for cond in filter_.must
        ), filter_


@pytest.mark.asyncio
async def test_non_legacy_delete_filter_is_unaffected(monkeypatch):
    """A normal (non-legacy) delete-by-document_id must NOT gain the
    IsEmptyCondition -- it's already precise (document_id is a fresh UUID per
    upload), the fix is scoped to the legacy: branch only."""
    from qdrant_client.models import IsEmptyCondition

    fake_client = _FakeDeleteQdrantClient(count=1)
    kb = _fake_kb()
    monkeypatch.setattr(rag_routes.state, "knowledge_bases", {"kb-1": kb})
    monkeypatch.setattr(rag_routes.state, "get_qdrant_client", lambda: fake_client)
    monkeypatch.setattr(rag_routes.state, "PG_AVAILABLE", False)
    monkeypatch.setattr(rag_routes, "invalidate_hybrid_index", lambda kb_id: None)

    await rag_routes.delete_document(
        kb_id="kb-1", document_id="doc-uuid-123", current_user={"sub": "u1"}
    )

    filter_ = fake_client.delete_filters[0]
    assert not any(isinstance(cond, IsEmptyCondition) for cond in filter_.must)
    assert filter_.must[0].key == "document_id"
    assert filter_.must[0].match.value == "doc-uuid-123"


# ── GET /v1/decision-stats wiring (system_routes.decision_stats) ──────────────
# The `AgentDecisionEngine.get_decision_stats` aggregation itself is covered in
# test_decision_engine_heuristics.py; these cover the ROUTE glue that was newly
# wired: the `available` flag and that the stats dict maps cleanly onto the
# DecisionStatsResponse fields (a key rename would silently drop data or 500).
@pytest.mark.asyncio
async def test_decision_stats_reports_unavailable_when_engine_is_none(monkeypatch):
    monkeypatch.setattr(system_routes.state, "decision_engine", None)

    resp = await system_routes.decision_stats()

    assert resp.available is False
    assert resp.total_decisions == 0
    assert resp.strategy_distribution == {}
    assert resp.complexity_distribution == {}
    assert resp.avg_confidence is None


@pytest.mark.asyncio
async def test_decision_stats_handles_engine_with_empty_history(monkeypatch):
    fake_engine = SimpleNamespace(get_decision_stats=lambda: {"total_decisions": 0})
    monkeypatch.setattr(system_routes.state, "decision_engine", fake_engine)

    resp = await system_routes.decision_stats()

    assert resp.available is True
    assert resp.total_decisions == 0
    assert resp.strategy_distribution == {}
    assert resp.avg_confidence is None


@pytest.mark.asyncio
async def test_decision_stats_wraps_full_engine_stats(monkeypatch):
    """The exact contract the route depends on: every key get_decision_stats
    returns for a non-empty history must map onto a DecisionStatsResponse field."""
    fake_engine = SimpleNamespace(
        get_decision_stats=lambda: {
            "total_decisions": 3,
            "strategy_distribution": {"basic": 2, "hierarchical": 1},
            "complexity_distribution": {"simple": 1, "moderate": 2},
            "avg_confidence": 0.75,
        }
    )
    monkeypatch.setattr(system_routes.state, "decision_engine", fake_engine)

    resp = await system_routes.decision_stats()

    assert resp.available is True
    assert resp.total_decisions == 3
    assert resp.strategy_distribution == {"basic": 2, "hierarchical": 1}
    assert resp.complexity_distribution == {"simple": 1, "moderate": 2}
    assert resp.avg_confidence == 0.75


# ── POST /v1/pipeline/{id}/query: retrieval-strategy selection ───────────────
# query_rag_pipeline's precedence logic (parent_context > hybrid > raptor >
# dense), metadata_filter binding, and GenerationError -> 503 mapping had ZERO
# direct test coverage (confirmed via `coverage`: lines 665-768 of routes/rag.py
# never executed by any unit test) despite being the actual query endpoint
# every RAG question goes through. run_query itself is faked -- these tests
# only exercise query_rag_pipeline's OWN logic (which retrieve_fn gets chosen,
# how errors map to HTTP status), not retrieval/generation themselves (already
# covered elsewhere in this file / test_rag_pipeline_corrective_rag.py etc).


def _unwrap(fn):
    """functools.partial(retrieve_relevant_documents, ...) -> retrieve_relevant_documents,
    so assertions can compare against the real underlying retrieve function
    regardless of whether metadata_filter/include_all_levels bound it."""
    return fn.func if isinstance(fn, functools.partial) else fn


def _fake_run_query_result(**overrides):
    result = {
        "answer": "the answer",
        "sources": [],
        "confidence": 0.9,
        "model_used": "llama3.2",
        "method": "standard",
        "method_details": {},
    }
    result.update(overrides)
    return result


@pytest.mark.asyncio
async def test_query_pipeline_404_for_unknown_pipeline():
    with _seed_state(rag_pipelines={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.query_rag_pipeline(
                "nope", models.QueryRequest(question="hi?")
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_query_pipeline_selects_parent_context_when_requested(monkeypatch):
    captured = {}

    async def fake_run_query(*, components, **kwargs):
        captured["retrieve_fn"] = components.retrieve
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(
                question="hi?", parent_context=True, hybrid=True, method="raptor"
            ),
            current_user={"sub": "u1"},
        )

    assert _unwrap(captured["retrieve_fn"]) is rag_routes.retrieve_parent_child
    assert resp.method_details["retrieval"] == "parent_context"
    # Both silently-overridden flags are recorded, not just dropped.
    degraded = resp.method_details["degraded"]
    assert any("hybrid flag ignored" in n for n in degraded)
    assert any("method=raptor ignored" in n for n in degraded)


@pytest.mark.asyncio
async def test_query_pipeline_selects_hybrid_when_available(monkeypatch):
    captured = {}

    async def fake_run_query(*, components, **kwargs):
        captured["retrieve_fn"] = components.retrieve
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    monkeypatch.setattr(rag_routes, "BM25_AVAILABLE", True)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?", hybrid=True),
            current_user={"sub": "u1"},
        )

    assert _unwrap(captured["retrieve_fn"]) is rag_routes.retrieve_hybrid
    assert resp.method_details["retrieval"] == "hybrid"
    assert "degraded" not in resp.method_details


@pytest.mark.asyncio
async def test_query_pipeline_hybrid_falls_back_to_dense_without_bm25(monkeypatch):
    captured = {}

    async def fake_run_query(*, components, **kwargs):
        captured["retrieve_fn"] = components.retrieve
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    monkeypatch.setattr(rag_routes, "BM25_AVAILABLE", False)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?", hybrid=True),
            current_user={"sub": "u1"},
        )

    assert _unwrap(captured["retrieve_fn"]) is rag_routes.retrieve_relevant_documents
    assert resp.method_details["retrieval"] == "dense"
    assert any("rank_bm25 unavailable" in n for n in resp.method_details["degraded"])


@pytest.mark.asyncio
async def test_query_pipeline_selects_raptor_collapsed_tree(monkeypatch):
    captured = {}

    async def fake_run_query(*, components, **kwargs):
        captured["retrieve_fn"] = components.retrieve
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?", method="raptor"),
            current_user={"sub": "u1"},
        )

    retrieve_fn = captured["retrieve_fn"]
    assert _unwrap(retrieve_fn) is rag_routes.retrieve_relevant_documents
    assert isinstance(retrieve_fn, functools.partial)
    assert retrieve_fn.keywords == {"include_all_levels": True}
    assert resp.method_details["retrieval"] == "raptor"


@pytest.mark.asyncio
async def test_query_pipeline_binds_metadata_filter_and_echoes_it(monkeypatch):
    captured = {}

    async def fake_run_query(*, components, **kwargs):
        captured["retrieve_fn"] = components.retrieve
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(
                question="hi?",
                metadata_filter=models.MetadataFilter(source="handbook.pdf"),
            ),
            current_user={"sub": "u1"},
        )

    retrieve_fn = captured["retrieve_fn"]
    assert isinstance(retrieve_fn, functools.partial)
    assert retrieve_fn.keywords["metadata_filter"].source == "handbook.pdf"
    assert resp.method_details["metadata_filter"] == {"source": "handbook.pdf"}


@pytest.mark.asyncio
async def test_query_pipeline_generation_error_maps_to_503_with_its_own_message(
    monkeypatch,
):
    async def fake_run_query(**kwargs):
        raise rag_routes.state.GenerationError(
            "failover primary down, served from fallback but it also failed"
        )

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.query_rag_pipeline(
                "p1",
                models.QueryRequest(question="hi?"),
                current_user={"sub": "u1"},
            )

    assert exc_info.value.status_code == 503
    assert "failover primary down" in exc_info.value.detail


@pytest.mark.asyncio
async def test_query_pipeline_generation_error_default_detail_when_empty(
    monkeypatch,
):
    async def fake_run_query(**kwargs):
        raise rag_routes.state.GenerationError("")

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.query_rag_pipeline(
                "p1",
                models.QueryRequest(question="hi?"),
                current_user={"sub": "u1"},
            )

    assert exc_info.value.status_code == 503
    assert "LLM backend unavailable" in exc_info.value.detail


@pytest.mark.asyncio
async def test_query_pipeline_passes_the_authenticated_users_id_to_run_query(
    monkeypatch,
):
    """#875: run_query must be told WHO is actually asking (the JWT sub), not
    a hardcoded/shared identity -- this is what makes per-user conversation
    history separation possible in the first place."""
    captured = {}

    async def fake_run_query(*, user_id, **kwargs):
        captured["user_id"] = user_id
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?"),
            current_user={"sub": "alice"},
        )

    assert captured["user_id"] == "alice"


@pytest.mark.asyncio
async def test_query_pipeline_defaults_user_id_to_anonymous_without_a_sub(
    monkeypatch,
):
    captured = {}

    async def fake_run_query(*, user_id, **kwargs):
        captured["user_id"] = user_id
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        await rag_routes.query_rag_pipeline(
            "p1", models.QueryRequest(question="hi?"), current_user={}
        )

    assert captured["user_id"] == "anonymous"


# ── #943: pipeline owner-scoping (query enforcement + list filter) ───────────


@pytest.mark.asyncio
async def test_query_403_for_a_non_owner(monkeypatch):
    """A user cannot query a pipeline someone else created -- the real
    owner-scoping boundary that protects both direct calls and the
    ask_<pipeline> chat tool (#943)."""

    async def fake_run_query(**kwargs):  # must never be reached
        raise AssertionError("run_query should not run for a rejected caller")

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {"knowledge_base_ids": [], "owner_user_id": "alice"}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.query_rag_pipeline(
                "p1",
                models.QueryRequest(question="hi?"),
                current_user={"sub": "bob", "role": "user"},
            )
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_query_allows_the_owner(monkeypatch):
    captured = {}

    async def fake_run_query(*, user_id, **kwargs):
        captured["ran"] = True
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {
        "knowledge_base_ids": [],
        "generation_config": {},
        "owner_user_id": "alice",
    }
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?"),
            current_user={"sub": "alice", "role": "user"},
        )
    assert captured.get("ran") is True


@pytest.mark.asyncio
async def test_query_allows_service_and_admin_on_an_owned_pipeline(monkeypatch):
    async def fake_run_query(**kwargs):
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {
        "knowledge_base_ids": [],
        "generation_config": {},
        "owner_user_id": "alice",
    }
    for principal in ({"sub": "svc", "role": "service"}, {"sub": "x", "role": "admin"}):
        with _seed_state(
            rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
        ):
            # No exception == allowed.
            await rag_routes.query_rag_pipeline(
                "p1", models.QueryRequest(question="hi?"), current_user=principal
            )


@pytest.mark.asyncio
async def test_query_allows_a_legacy_null_owner_pipeline(monkeypatch):
    """Pipelines created before #943 have owner_user_id=None and stay open, so
    the migration doesn't lock everyone out of existing pipelines."""

    async def fake_run_query(**kwargs):
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    pipeline = {
        "knowledge_base_ids": [],
        "generation_config": {},
        "owner_user_id": None,
    }
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?"),
            current_user={"sub": "anyone", "role": "user"},
        )


def test_list_pipelines_owner_filter_returns_own_plus_legacy():
    client = _rag_router_client()
    pipes = {
        "a": {
            "id": "a",
            "name": "A",
            "knowledge_base_ids": [],
            "created_at": "t",
            "owner_user_id": "alice",
        },
        "b": {
            "id": "b",
            "name": "B",
            "knowledge_base_ids": [],
            "created_at": "t",
            "owner_user_id": "bob",
        },
        "c": {
            "id": "c",
            "name": "C",
            "knowledge_base_ids": [],
            "created_at": "t",
            "owner_user_id": None,
        },
    }
    with _seed_state(rag_pipelines=pipes):
        resp = client.get("/v1/pipeline?owner_user_id=alice")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {"a", "c"}  # own + legacy null-owner, never bob's


def test_list_pipelines_without_owner_filter_returns_all():
    client = _rag_router_client()
    pipes = {
        "a": {
            "id": "a",
            "name": "A",
            "knowledge_base_ids": [],
            "created_at": "t",
            "owner_user_id": "alice",
        },
        "b": {
            "id": "b",
            "name": "B",
            "knowledge_base_ids": [],
            "created_at": "t",
            "owner_user_id": "bob",
        },
    }
    with _seed_state(rag_pipelines=pipes):
        resp = client.get("/v1/pipeline")
    assert resp.status_code == 200
    assert {item["id"] for item in resp.json()["items"]} == {"a", "b"}


# ── POST /v1/pipeline/{id}/conversations/{conversation_id}/share ────────────
# #875's optional half: an explicit opt-in that lets a second user continue a
# conversation the caller started, instead of each user's history staying
# permanently siloed.


class _FakeShareRepo:
    def __init__(self, allow=True):
        self._allow = allow
        self.calls = []

    async def share_conversation(self, user_id, conversation_id):
        self.calls.append((user_id, conversation_id))
        if not self._allow:
            raise PermissionError(f"{user_id} does not own {conversation_id}")
        return True


@pytest.mark.asyncio
async def test_share_conversation_404_for_unknown_pipeline():
    with _seed_state(rag_pipelines={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.share_conversation(
                "nope", "conv1", current_user={"sub": "alice"}
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_share_conversation_503_without_a_conversation_repository():
    # PG_AVAILABLE=False makes ensure_conversation_repository() return None
    # deterministically (no lazy pool attempt), i.e. conversational storage
    # genuinely unavailable -> 503.
    with _seed_state(
        rag_pipelines={"p1": {}}, conversation_repository=None, PG_AVAILABLE=False
    ):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.share_conversation(
                "p1", "conv1", current_user={"sub": "alice"}
            )
    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_share_conversation_succeeds_for_the_owner():
    repo = _FakeShareRepo(allow=True)
    with _seed_state(rag_pipelines={"p1": {}}, conversation_repository=repo):
        result = await rag_routes.share_conversation(
            "p1", "conv1", current_user={"sub": "alice"}
        )

    assert result == {"conversation_id": "conv1", "shared": True}
    assert repo.calls == [("alice", "conv1")]


@pytest.mark.asyncio
async def test_share_conversation_403_for_a_non_owner():
    repo = _FakeShareRepo(allow=False)
    with _seed_state(rag_pipelines={"p1": {}}, conversation_repository=repo):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.share_conversation(
                "p1", "conv1", current_user={"sub": "intruder"}
            )

    assert exc_info.value.status_code == 403


# ── GET /capabilities (system_routes.capabilities) ──────────────────────────
# Reports which RAG methods/enhancers/retrievers are active on this host --
# had zero direct coverage despite driving the client's RagPipelinesPage
# capability gating (#485).


@pytest.mark.asyncio
async def test_capabilities_reports_availability_from_state(monkeypatch):
    fake_state = SimpleNamespace(
        ensure_conversation_repository=AsyncMock(return_value=object()),
        hyde_expander=object(),
        self_rag_pipeline=None,
        decision_engine=object(),
        corrective_pipeline=None,
        reranker=object(),
        compressor=None,
    )
    monkeypatch.setattr(system_routes, "state", fake_state)
    monkeypatch.setattr(system_routes, "_sentence_transformers_available", lambda: True)
    monkeypatch.setattr(system_routes, "_bm25_available", lambda: True)

    result = await system_routes.capabilities()

    assert result["methods"] == {
        "standard": True,
        "conversational": True,
        "hyde": True,
        "self_rag": False,
        "auto": True,
        "corrective": False,
        "raptor": True,
    }
    assert result["enhancers"]["rerank"] == {
        "available": True,
        "backend": "cross_encoder",
    }
    assert result["enhancers"]["compress"] == {"available": False}
    assert result["retrievers"]["hybrid"] == {"available": True}
    assert result["optional_deps"] == {
        "sentence_transformers": True,
        "rank_bm25": True,
    }


@pytest.mark.asyncio
async def test_capabilities_reports_llm_rerank_backend_without_sentence_transformers(
    monkeypatch,
):
    fake_state = SimpleNamespace(
        ensure_conversation_repository=AsyncMock(return_value=None),
        hyde_expander=None,
        self_rag_pipeline=None,
        decision_engine=None,
        corrective_pipeline=None,
        reranker=object(),
        compressor=None,
    )
    monkeypatch.setattr(system_routes, "state", fake_state)
    monkeypatch.setattr(
        system_routes, "_sentence_transformers_available", lambda: False
    )
    monkeypatch.setattr(system_routes, "_bm25_available", lambda: False)

    result = await system_routes.capabilities()

    assert result["enhancers"]["rerank"] == {"available": True, "backend": "llm"}
    assert result["retrievers"]["hybrid"] == {"available": False}


# ── ensure_conversation_repository: lazy recovery after a boot where the PG pool
#    wasn't ready yet (#949). Before this the repo was bound once at startup and,
#    if PG was still in crash-recovery then, stayed None (503) for the whole
#    container lifetime while every other PG-backed feature recovered lazily. ──


@pytest.mark.asyncio
async def test_ensure_conversation_repository_lazily_builds_when_pool_recovers(
    monkeypatch,
):
    state = rag_routes.state
    monkeypatch.setattr(state, "conversation_repository", None)
    monkeypatch.setattr(state, "CONVERSATION_REPO_AVAILABLE", True)
    monkeypatch.setattr(state, "PG_AVAILABLE", True)
    fake_pool = object()
    monkeypatch.setattr(
        state.pg_client, "get_pg_connection", AsyncMock(return_value=fake_pool)
    )
    built = {}

    class _FakeRepo:
        def __init__(self, pool):
            built["pool"] = pool

    monkeypatch.setattr(state, "ConversationRepository", _FakeRepo)

    repo = await state.ensure_conversation_repository()
    assert isinstance(repo, _FakeRepo)
    assert built["pool"] is fake_pool
    # Cached: a second call returns the same instance without rebuilding.
    assert await state.ensure_conversation_repository() is repo


@pytest.mark.asyncio
async def test_ensure_conversation_repository_stays_none_when_pool_unavailable(
    monkeypatch,
):
    state = rag_routes.state
    monkeypatch.setattr(state, "conversation_repository", None)
    monkeypatch.setattr(state, "CONVERSATION_REPO_AVAILABLE", True)
    monkeypatch.setattr(state, "PG_AVAILABLE", True)
    monkeypatch.setattr(
        state.pg_client,
        "get_pg_connection",
        AsyncMock(side_effect=RuntimeError("db down")),
    )
    assert await state.ensure_conversation_repository() is None


# ── GET /health (system_routes.health_check) ────────────────────────────────


@pytest.mark.asyncio
async def test_health_check_all_healthy_is_200(monkeypatch):
    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: SimpleNamespace(get_collections=lambda: None),
        OLLAMA_AVAILABLE=True,
        ollama_manager=SimpleNamespace(_initialized=True),
        knowledge_bases={},
        rag_pipelines={},
    )
    monkeypatch.setattr(system_routes, "state", fake_state)

    response = await system_routes.health_check()

    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_check_qdrant_down_is_503(monkeypatch):
    def _boom():
        raise ConnectionError("qdrant unreachable")

    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: SimpleNamespace(get_collections=_boom),
        OLLAMA_AVAILABLE=True,
        ollama_manager=SimpleNamespace(_initialized=True),
        knowledge_bases={},
        rag_pipelines={},
    )
    monkeypatch.setattr(system_routes, "state", fake_state)

    response = await system_routes.health_check()

    assert response.status_code == 503
    body = json.loads(response.body)
    assert body["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_health_check_ollama_unavailable_is_degraded_not_down(monkeypatch):
    fake_state = SimpleNamespace(
        get_qdrant_client=lambda: SimpleNamespace(get_collections=lambda: None),
        OLLAMA_AVAILABLE=False,
        ollama_manager=SimpleNamespace(_initialized=False),
        knowledge_bases={"kb1": {}},
        rag_pipelines={},
    )
    monkeypatch.setattr(system_routes, "state", fake_state)

    response = await system_routes.health_check()

    # Ollama is non-critical -- still 200, but reported as degraded, not silently healthy.
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["status"] == "degraded"
    assert body["knowledge_bases"] == 1


# ── routes/rag.py coverage gaps: KB/pipeline CRUD's PG-persist branches and ───
# delete_knowledge_base/create_rag_pipeline/delete_rag_pipeline's bodies ──────
# (73% coverage -- create_rag_pipeline and delete_rag_pipeline's actual bodies
# were ENTIRELY untested, only their auth-gate/update siblings had coverage;
# every CRUD route's `if state.PG_AVAILABLE:` try/except-warn branch was
# likewise never exercised with PG_AVAILABLE=True).


@pytest.mark.asyncio
async def test_create_knowledge_base_saves_to_postgres_when_available(monkeypatch):
    saved = {}

    async def fake_save(kb_id, kb_data):
        saved["kb_id"] = kb_id
        saved["kb_data"] = kb_data

    with _seed_state(knowledge_bases={}, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "save_kb_to_postgres", fake_save)
        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(create_collection=lambda **kwargs: None),
        )
        resp = await rag_routes.create_knowledge_base(
            _KBCreate(), current_user={"sub": "alice", "role": "user"}
        )

    assert saved["kb_id"] == resp.id
    assert saved["kb_data"]["name"] == "test-kb"
    # Tenancy: creator recorded + default private, persisted + returned.
    assert saved["kb_data"]["owner_id"] == "alice"
    assert saved["kb_data"]["visibility"] == "private"
    assert resp.owner_id == "alice"
    assert resp.visibility == "private"


def test_list_knowledge_bases_owner_filter_returns_own_plus_legacy():
    client = _rag_router_client()
    kbs = {
        "a": {**_kb("a"), "owner_id": "alice"},
        "b": {**_kb("b"), "owner_id": "bob"},
        "c": {**_kb("c"), "owner_id": None},  # legacy/unowned
    }
    with _seed_state(knowledge_bases=kbs):
        resp = client.get("/v1/knowledge-bases?owner_id=alice")
    assert resp.status_code == 200
    ids = {item["id"] for item in resp.json()["items"]}
    assert ids == {"a", "c"}  # own + legacy null-owner, never bob's


@pytest.mark.asyncio
async def test_create_knowledge_base_pg_save_failure_is_non_fatal(monkeypatch):
    async def fake_save(kb_id, kb_data):
        raise RuntimeError("db unreachable")

    with _seed_state(knowledge_bases={}, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "save_kb_to_postgres", fake_save)
        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(create_collection=lambda **kwargs: None),
        )
        resp = await rag_routes.create_knowledge_base(
            _KBCreate(), current_user={"sub": "alice", "role": "user"}
        )

    assert resp.name == "test-kb"  # PG failure logged, not raised


def test_get_knowledge_base_404():
    client = _rag_router_client()
    with _seed_state(knowledge_bases={}):
        resp = client.get("/v1/knowledge-bases/nope")
    assert resp.status_code == 404


def test_get_knowledge_base_returns_it():
    client = _rag_router_client()
    with _seed_state(knowledge_bases={"kb1": _kb("kb1")}):
        resp = client.get("/v1/knowledge-bases/kb1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "kb1"


@pytest.mark.asyncio
async def test_update_kb_saves_to_postgres_when_available(monkeypatch):
    saved = {}

    async def fake_save(kb_id, kb_data):
        saved["kb_id"] = kb_id

    kb = _kb_full("kb1")
    with _seed_state(knowledge_bases={"kb1": kb}, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "save_kb_to_postgres", fake_save)
        await rag_routes.update_knowledge_base(
            "kb1", models.KnowledgeBaseUpdate(name="new"), {"sub": "1"}
        )

    assert saved["kb_id"] == "kb1"


@pytest.mark.asyncio
async def test_update_kb_pg_save_failure_is_non_fatal(monkeypatch):
    async def fake_save(kb_id, kb_data):
        raise RuntimeError("db unreachable")

    kb = _kb_full("kb1")
    with _seed_state(knowledge_bases={"kb1": kb}, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "save_kb_to_postgres", fake_save)
        resp = await rag_routes.update_knowledge_base(
            "kb1", models.KnowledgeBaseUpdate(name="new"), {"sub": "1"}
        )

    assert resp.name == "new"  # PG failure logged, not raised


# ── DELETE /v1/knowledge-bases/{id}: entirely untested before this file ──────


@pytest.mark.asyncio
async def test_delete_knowledge_base_404():
    with _seed_state(knowledge_bases={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.delete_knowledge_base("nope", {"sub": "1"})
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_knowledge_base_success_drops_qdrant_collection(monkeypatch):
    deleted = {}
    kbs = {"kb1": _kb("kb1")}

    with _seed_state(knowledge_bases=kbs, PG_AVAILABLE=False):
        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(
                delete_collection=lambda collection_name: deleted.update(
                    {"collection_name": collection_name}
                )
            ),
        )
        resp = await rag_routes.delete_knowledge_base("kb1", {"sub": "1"})

    assert resp == {"message": "Knowledge base deleted", "id": "kb1"}
    assert deleted["collection_name"] == "kb1"
    assert (
        "kb1" not in kbs
    )  # popped from the SAME dict object state.knowledge_bases held


@pytest.mark.asyncio
async def test_delete_knowledge_base_tolerates_qdrant_failure(monkeypatch):
    kbs = {"kb1": _kb("kb1")}

    with _seed_state(knowledge_bases=kbs, PG_AVAILABLE=False):

        def boom(collection_name):
            raise ConnectionError("qdrant down")

        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(delete_collection=boom),
        )
        resp = await rag_routes.delete_knowledge_base("kb1", {"sub": "1"})

    assert resp["id"] == "kb1"  # Qdrant failure logged, not raised
    assert "kb1" not in kbs


@pytest.mark.asyncio
async def test_delete_knowledge_base_pg_delete_failure_is_non_fatal(monkeypatch):
    kbs = {"kb1": _kb("kb1")}

    async def boom(kb_id):
        raise RuntimeError("db unreachable")

    with _seed_state(knowledge_bases=kbs, PG_AVAILABLE=True):
        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(delete_collection=lambda collection_name: None),
        )
        monkeypatch.setattr(rag_routes.state, "delete_kb_from_postgres", boom)
        resp = await rag_routes.delete_knowledge_base("kb1", {"sub": "1"})

    assert resp["id"] == "kb1"
    assert "kb1" not in kbs


# ── upload_document / list_documents: 404 branches ───────────────────────────


@pytest.mark.asyncio
async def test_upload_document_404_unknown_kb():
    with _seed_state(knowledge_bases={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.upload_document("nope", file=None, build_tree=False)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_documents_404_unknown_kb():
    with _seed_state(knowledge_bases={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.list_documents("nope")
    assert exc_info.value.status_code == 404


# ── delete_document: 404 branches + PG-persist branch ────────────────────────


@pytest.mark.asyncio
async def test_delete_document_404_unknown_kb():
    with _seed_state(knowledge_bases={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.delete_document("nope", "doc1", {"sub": "1"})
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_404_when_no_chunks_match(monkeypatch):
    kb = _kb("kb1")
    with _seed_state(knowledge_bases={"kb1": kb}, PG_AVAILABLE=False):
        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(count=lambda **kw: SimpleNamespace(count=0)),
        )
        with pytest.raises(Exception) as exc_info:
            await rag_routes.delete_document("kb1", "doc1", {"sub": "1"})
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_pg_save_failure_is_non_fatal(monkeypatch):
    kb = _kb_full("kb1")

    async def boom(kb_id, kb_data):
        raise RuntimeError("db unreachable")

    with _seed_state(knowledge_bases={"kb1": kb}, PG_AVAILABLE=True):
        monkeypatch.setattr(
            rag_routes.state,
            "get_qdrant_client",
            lambda: SimpleNamespace(
                count=lambda **kw: SimpleNamespace(count=2),
                delete=lambda **kw: None,
            ),
        )
        monkeypatch.setattr(rag_routes, "invalidate_hybrid_index", lambda kb_id: None)
        monkeypatch.setattr(rag_routes.state, "save_kb_to_postgres", boom)
        resp = await rag_routes.delete_document("kb1", "doc1", {"sub": "1"})

    assert resp == {"message": "Document deleted", "id": "doc1"}
    assert kb["document_count"] == 2  # decremented despite the PG failure


# ── create_rag_pipeline: entirely untested before this file ──────────────────


@pytest.mark.asyncio
async def test_create_rag_pipeline_success():
    with _seed_state(
        rag_pipelines={}, knowledge_bases={"kb1": _kb("kb1")}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.create_rag_pipeline(
            models.RAGPipelineCreate(name="p", knowledge_base_ids=["kb1"]),
            current_user={"sub": "alice", "role": "user"},
        )
        assert resp.pipeline_id in rag_routes.state.rag_pipelines
        # #943: creator recorded so the pipeline can be owner-scoped later.
        assert (
            rag_routes.state.rag_pipelines[resp.pipeline_id]["owner_user_id"] == "alice"
        )

    assert resp.name == "p"
    assert resp.knowledge_base_ids == ["kb1"]


@pytest.mark.asyncio
async def test_create_rag_pipeline_unknown_kb_404():
    with _seed_state(rag_pipelines={}, knowledge_bases={}, PG_AVAILABLE=False):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.create_rag_pipeline(
                models.RAGPipelineCreate(name="p", knowledge_base_ids=["nope"])
            )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_rag_pipeline_saves_to_postgres_when_available(monkeypatch):
    saved = {}

    async def fake_save(pipeline_id, data):
        saved["pipeline_id"] = pipeline_id

    with _seed_state(
        rag_pipelines={}, knowledge_bases={"kb1": _kb("kb1")}, PG_AVAILABLE=True
    ):
        monkeypatch.setattr(rag_routes.state, "save_pipeline_to_postgres", fake_save)
        resp = await rag_routes.create_rag_pipeline(
            models.RAGPipelineCreate(name="p", knowledge_base_ids=["kb1"]),
            current_user={"sub": "alice", "role": "user"},
        )

    assert saved["pipeline_id"] == resp.pipeline_id


@pytest.mark.asyncio
async def test_create_rag_pipeline_pg_save_failure_is_non_fatal(monkeypatch):
    async def boom(pipeline_id, data):
        raise RuntimeError("db unreachable")

    with _seed_state(
        rag_pipelines={}, knowledge_bases={"kb1": _kb("kb1")}, PG_AVAILABLE=True
    ):
        monkeypatch.setattr(rag_routes.state, "save_pipeline_to_postgres", boom)
        resp = await rag_routes.create_rag_pipeline(
            models.RAGPipelineCreate(name="p", knowledge_base_ids=["kb1"]),
            current_user={"sub": "alice", "role": "user"},
        )

    assert resp.name == "p"  # PG failure logged, not raised


# ── get_rag_pipeline: 404 + happy path ────────────────────────────────────────


def test_get_rag_pipeline_404():
    client = _rag_router_client()
    with _seed_state(rag_pipelines={}):
        resp = client.get("/v1/pipeline/nope")
    assert resp.status_code == 404


def test_get_rag_pipeline_returns_it():
    client = _rag_router_client()
    pipe = {
        "id": "p1",
        "name": "n",
        "knowledge_base_ids": [],
        "retrieval_config": {},
        "generation_config": {},
        "created_at": "2026-01-01T00:00:00Z",
    }
    with _seed_state(rag_pipelines={"p1": pipe}):
        resp = client.get("/v1/pipeline/p1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "p1"


@pytest.mark.asyncio
async def test_update_pipeline_saves_to_postgres_when_available(monkeypatch):
    saved = {}

    async def fake_save(pipeline_id, data):
        saved["pipeline_id"] = pipeline_id

    pipe = {"id": "p1", "name": "old", "knowledge_base_ids": [], "created_at": "x"}
    with _seed_state(rag_pipelines={"p1": pipe}, knowledge_bases={}, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "save_pipeline_to_postgres", fake_save)
        await rag_routes.update_rag_pipeline(
            "p1", models.RAGPipelineUpdate(name="renamed"), {"sub": "1"}
        )

    assert saved["pipeline_id"] == "p1"


@pytest.mark.asyncio
async def test_update_pipeline_pg_save_failure_is_non_fatal(monkeypatch):
    async def boom(pipeline_id, data):
        raise RuntimeError("db unreachable")

    pipe = {"id": "p1", "name": "old", "knowledge_base_ids": [], "created_at": "x"}
    with _seed_state(rag_pipelines={"p1": pipe}, knowledge_bases={}, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "save_pipeline_to_postgres", boom)
        resp = await rag_routes.update_rag_pipeline(
            "p1", models.RAGPipelineUpdate(name="renamed"), {"sub": "1"}
        )

    assert resp["name"] == "renamed"  # PG failure logged, not raised


# ── delete_rag_pipeline: entirely untested before this file ──────────────────


@pytest.mark.asyncio
async def test_delete_rag_pipeline_404():
    with _seed_state(rag_pipelines={}):
        with pytest.raises(Exception) as exc_info:
            await rag_routes.delete_rag_pipeline("nope", {"sub": "1"})
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_rag_pipeline_success():
    pipe = {"id": "p1", "name": "n", "knowledge_base_ids": [], "created_at": "x"}
    pipelines = {"p1": pipe}
    with _seed_state(rag_pipelines=pipelines, PG_AVAILABLE=False):
        resp = await rag_routes.delete_rag_pipeline("p1", {"sub": "1"})

    assert resp == {"message": "RAG pipeline deleted", "id": "p1"}
    assert "p1" not in pipelines  # popped from the SAME dict object state held


@pytest.mark.asyncio
async def test_delete_rag_pipeline_pg_delete_failure_is_non_fatal(monkeypatch):
    pipe = {"id": "p1", "name": "n", "knowledge_base_ids": [], "created_at": "x"}
    pipelines = {"p1": pipe}

    async def boom(pipeline_id):
        raise RuntimeError("db unreachable")

    with _seed_state(rag_pipelines=pipelines, PG_AVAILABLE=True):
        monkeypatch.setattr(rag_routes.state, "delete_pipeline_from_postgres", boom)
        resp = await rag_routes.delete_rag_pipeline("p1", {"sub": "1"})

    assert resp["id"] == "p1"
    assert "p1" not in pipelines


# ── query_rag_pipeline: hybrid takes precedence over raptor (degraded note) ──


@pytest.mark.asyncio
async def test_query_pipeline_hybrid_precedence_over_raptor_records_degraded_note(
    monkeypatch,
):
    async def fake_run_query(*, components, **kwargs):
        return _fake_run_query_result()

    monkeypatch.setattr(rag_routes.state, "run_query", fake_run_query)
    monkeypatch.setattr(rag_routes, "BM25_AVAILABLE", True)
    pipeline = {"knowledge_base_ids": [], "generation_config": {}}
    with _seed_state(
        rag_pipelines={"p1": pipeline}, knowledge_bases={}, PG_AVAILABLE=False
    ):
        resp = await rag_routes.query_rag_pipeline(
            "p1",
            models.QueryRequest(question="hi?", hybrid=True, method="raptor"),
            current_user={"sub": "u1"},
        )

    assert resp.method_details["retrieval"] == "hybrid"
    assert any("method=raptor ignored" in n for n in resp.method_details["degraded"])


# ── core/state.py: get_qdrant_client (creates once, reuses) ──────────────────
# core.state can't be freshly re-imported by its own test file (it registers
# process-global Prometheus Counters/Histograms -- a second import raises
# DuplicateTimeseries, per this file's own _isolated_import docstring), so
# this exercises it via rag_routes.state, the SAME already-loaded module
# object every other state-dependent test in this file already patches
# attributes on.


def test_get_qdrant_client_creates_once_and_reuses(monkeypatch):
    created_urls = []

    class _FakeQdrantClient:
        def __init__(self, url):
            created_urls.append(url)

    monkeypatch.setattr(rag_routes.state, "QdrantClient", _FakeQdrantClient)
    monkeypatch.setattr(rag_routes.state, "_qdrant_client", None)

    first = rag_routes.state.get_qdrant_client()
    second = rag_routes.state.get_qdrant_client()

    assert first is second
    assert len(created_urls) == 1


# ── system.py: _sentence_transformers_available / _bm25_available's own ─────
# bodies (always mocked out in the capabilities tests above), root(), and
# initialize_ollama's success path -- none had ever executed directly.


def test_sentence_transformers_available_matches_find_spec():
    import importlib.util

    expected = importlib.util.find_spec("sentence_transformers") is not None
    assert system_routes._sentence_transformers_available() is expected


def test_bm25_available_matches_find_spec():
    import importlib.util

    expected = importlib.util.find_spec("rank_bm25") is not None
    assert system_routes._bm25_available() is expected


@pytest.mark.asyncio
async def test_root_reports_name_version_and_ollama_availability():
    fake_state = SimpleNamespace(OLLAMA_AVAILABLE=True)
    saved = system_routes.state
    system_routes.state = fake_state
    try:
        result = await system_routes.root()
    finally:
        system_routes.state = saved

    assert result["name"] == "Minder RAG Pipeline"
    assert result["status"] == "operational"
    assert result["ollama_available"] is True


@pytest.mark.asyncio
async def test_initialize_ollama_success_returns_confirmation(monkeypatch):
    initialized = {"called": False}

    async def fake_initialize():
        initialized["called"] = True

    monkeypatch.setattr(
        system_routes.state,
        "ollama_manager",
        type("M", (), {"initialize": staticmethod(fake_initialize)})(),
    )

    result = await system_routes.initialize_ollama()

    assert initialized["called"] is True
    assert result == {"message": "Ollama client initialized successfully"}
