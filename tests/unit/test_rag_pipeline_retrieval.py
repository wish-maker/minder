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

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "rag-pipeline"

_COLLISION_PRONE_NAMES = ("core", "routes", "models", "rag", "config", "domain")


def _isolated_import(module_path: str):
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
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


retrieval = _isolated_import("core.retrieval")


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
