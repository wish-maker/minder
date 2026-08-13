"""Unit tests for rag-pipeline/domain/rerankers/cross_encoder.CrossEncoderReranker.

The cross-encoder model is disabled by default on the Pi (CPU/memory), so the
FALLBACK path — return the documents in their original order carrying their own
`score` (0.0 when missing), capped at top_k — is what actually runs in production
and had zero coverage. These lock the validation guards and that fallback (no model
loads; the heavy sentence-transformers CrossEncoder is never imported).

Loaded by-path because the service dir is hyphenated (`rag-pipeline`).
"""

import importlib.util
from pathlib import Path

import pytest

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "rerankers"
    / "cross_encoder.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_cross_encoder", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CrossEncoderReranker = _load().CrossEncoderReranker

_DOCS = [
    {"text": "alpha", "score": 0.1},
    {"text": "beta", "score": 0.9},
    {"text": "gamma"},  # missing score -> defaults to 0.0
]


def test_default_is_fallback_disabled():
    assert CrossEncoderReranker().use_reranker is False


def test_rerank_empty_query_raises():
    with pytest.raises(ValueError):
        CrossEncoderReranker().rerank("", _DOCS)


def test_rerank_no_documents_returns_empty():
    assert CrossEncoderReranker().rerank("q", []) == []


def test_rerank_nonpositive_top_k_raises():
    with pytest.raises(ValueError):
        CrossEncoderReranker().rerank("q", _DOCS, top_k=0)


def test_fallback_preserves_order_and_scores():
    # Fallback keeps original order and each doc's own score (0.0 when missing).
    out = CrossEncoderReranker().rerank("q", _DOCS, top_k=10)
    assert [d["text"] for d, _ in out] == ["alpha", "beta", "gamma"]
    assert [s for _, s in out] == [0.1, 0.9, 0.0]


def test_fallback_respects_top_k():
    out = CrossEncoderReranker().rerank("q", _DOCS, top_k=2)
    assert len(out) == 2
    assert [d["text"] for d, _ in out] == ["alpha", "beta"]


def test_fallback_used_when_model_load_fails():
    # Force the lazy model property down its except branch: sentence_transformers
    # isn't installed in the test image, so `self.model` resolves to False and
    # use_reranker stays False -> fallback. Accessing .model must not raise.
    r = CrossEncoderReranker()
    assert r.model is False
    assert r.use_reranker is False
    out = r.rerank("q", _DOCS, top_k=1)
    assert out == [({"text": "alpha", "score": 0.1}, 0.1)]
