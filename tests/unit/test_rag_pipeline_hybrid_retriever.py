"""Direct unit tests for HybridSearchRetriever (domain/retrievers/hybrid.py).

The module's own docstring says it has "NO external dependencies" and is a
pure domain component -- yet it was only ever exercised indirectly, via a
monkeypatched `hybrid_search` in the route-level retrieval tests. That left
its actual BM25 indexing, score-combination, sorting, and dense-only-fallback
logic with zero real coverage (20% per `coverage run`, essentially just the
constructor's happy path).
"""

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "retrievers"
    / "hybrid.py"
)


def _load_hybrid_module():
    spec = importlib.util.spec_from_file_location(
        "rag_pipeline_hybrid_retriever", _MODULE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


hybrid = _load_hybrid_module()
HybridSearchRetriever = hybrid.HybridSearchRetriever


class _Hit:
    def __init__(self, id_, payload, score):
        self.id = id_
        self.payload = payload
        self.score = score


def _docs():
    return [
        {"_id": "d1", "text": "Acme makes widgets and gadgets in Ohio."},
        {"_id": "d2", "text": "The stock market closed higher today."},
        {"_id": "d3", "text": "Widgets are Acme's flagship product line."},
    ]


class TestInit:
    def test_rejects_alpha_below_range(self):
        with pytest.raises(ValueError, match="alpha must be in"):
            HybridSearchRetriever(alpha=-0.1)

    def test_rejects_alpha_above_range(self):
        with pytest.raises(ValueError, match="alpha must be in"):
            HybridSearchRetriever(alpha=1.1)

    def test_accepts_boundary_values(self):
        HybridSearchRetriever(alpha=0.0)
        HybridSearchRetriever(alpha=1.0)


class TestIndexDocuments:
    def test_empty_kb_id_raises(self):
        retriever = HybridSearchRetriever()
        with pytest.raises(ValueError, match="kb_id cannot be empty"):
            retriever.index_documents("", _docs())

    def test_no_documents_is_a_noop(self):
        retriever = HybridSearchRetriever()
        retriever.index_documents("kb1", [])
        assert "kb1" not in retriever.sparse_index
        assert "kb1" not in retriever.documents

    def test_builds_bm25_index_for_valid_documents(self):
        retriever = HybridSearchRetriever()
        retriever.index_documents("kb1", _docs())
        assert "kb1" in retriever.sparse_index
        assert retriever.documents["kb1"] == _docs()


class TestSparseSearch:
    def test_unindexed_kb_returns_empty(self):
        retriever = HybridSearchRetriever()
        assert retriever._sparse_search("no-such-kb", "widgets", 5) == {}

    def test_empty_query_tokens_returns_empty(self):
        retriever = HybridSearchRetriever()
        retriever.index_documents("kb1", _docs())
        assert retriever._sparse_search("kb1", "   ", 5) == {}

    def test_returns_scores_favoring_the_matching_document(self):
        retriever = HybridSearchRetriever()
        retriever.index_documents("kb1", _docs())
        scores = retriever._sparse_search("kb1", "widgets acme", 5)
        assert "d1" in scores and "d3" in scores
        # d2 (stock market) shares no query terms -- BM25 gives it 0, and this
        # implementation only returns docs whose index rank made the top-k, so
        # it may be entirely absent; either is fine, but if present it must
        # score strictly below the actually-matching documents.
        if "d2" in scores:
            assert scores["d2"] < scores["d1"]
            assert scores["d2"] < scores["d3"]


class TestNormalizeScore:
    def test_empty_scores_returns_zero(self):
        retriever = HybridSearchRetriever()
        assert retriever._normalize_score(5.0, {}) == 0.0

    def test_zero_max_returns_zero(self):
        retriever = HybridSearchRetriever()
        assert retriever._normalize_score(0.0, {"a": 0.0, "b": 0.0}) == 0.0

    def test_divides_by_the_max_reference_score(self):
        retriever = HybridSearchRetriever()
        result = retriever._normalize_score(5.0, {"a": 10.0, "b": 5.0})
        assert result == 0.5


class TestHybridSearch:
    @pytest.mark.asyncio
    async def test_empty_kb_id_raises(self):
        retriever = HybridSearchRetriever()
        with pytest.raises(ValueError, match="kb_id cannot be empty"):
            await retriever.hybrid_search("", [0.1], "q", [_Hit("d1", {}, 0.5)])

    @pytest.mark.asyncio
    async def test_non_positive_top_k_raises(self):
        retriever = HybridSearchRetriever()
        with pytest.raises(ValueError, match="top_k must be positive"):
            await retriever.hybrid_search(
                "kb1", [0.1], "q", [_Hit("d1", {}, 0.5)], top_k=0
            )

    @pytest.mark.asyncio
    async def test_no_dense_results_returns_empty(self):
        retriever = HybridSearchRetriever()
        result = await retriever.hybrid_search("kb1", [0.1], "q", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_combines_dense_and_sparse_and_sorts_descending(self):
        retriever = HybridSearchRetriever(alpha=0.5)
        retriever.index_documents("kb1", _docs())
        dense_results = [
            _Hit("d1", {"_id": "d1"}, 0.9),
            _Hit("d2", {"_id": "d2"}, 0.4),
        ]
        results = await retriever.hybrid_search(
            "kb1", [0.1], "widgets acme", dense_results, top_k=3
        )
        doc_ids = [doc_id for doc_id, _ in results]
        # d3 is sparse-only (BM25 matches "widgets"/"acme" but it was never a
        # dense hit) -- it must still surface via the sparse contribution.
        assert "d3" in doc_ids
        scores = dict(results)
        # Results must actually be sorted descending by combined score.
        assert list(scores.values()) == sorted(scores.values(), reverse=True)

    @pytest.mark.asyncio
    async def test_falls_back_to_dense_only_order_on_internal_error(self):
        retriever = HybridSearchRetriever()
        retriever.index_documents("kb1", _docs())
        retriever._sparse_search = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
        dense_results = [
            _Hit("d1", {"_id": "d1"}, 0.9),
            _Hit("d2", {"_id": "d2"}, 0.4),
        ]
        results = await retriever.hybrid_search(
            "kb1", [0.1], "widgets", dense_results, top_k=5
        )
        assert results == [("d1", 0.9), ("d2", 0.4)]
