"""Unit tests for rag-pipeline/domain/rerankers/cross_encoder.CrossEncoderReranker.

The cross-encoder model is disabled by default on the Pi (CPU/memory), so the
FALLBACK path — return the documents in their original order carrying their own
`score` (0.0 when missing), capped at top_k — is what actually runs in production
and had zero coverage. These lock the validation guards and that fallback (no model
loads; the heavy sentence-transformers CrossEncoder is never imported).

Loaded by-path because the service dir is hyphenated (`rag-pipeline`).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

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


class _FakeCrossEncoderModel:
    """Duck-types sentence_transformers.CrossEncoder well enough to exercise
    the real (non-fallback) load/predict path without the actual heavy dep."""

    def __init__(self, model_name, device=None, max_length=None):
        self.model_name = model_name
        self.device = device
        self.max_length = max_length

    def predict(self, pairs):
        return [0.2, 0.8, 0.5][: len(pairs)]


def _inject_fake_sentence_transformers(monkeypatch, cross_encoder_cls):
    fake_module = ModuleType("sentence_transformers")
    fake_module.CrossEncoder = cross_encoder_cls
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)


def test_model_property_loads_and_caches_when_dependency_available(monkeypatch):
    _inject_fake_sentence_transformers(monkeypatch, _FakeCrossEncoderModel)

    r = CrossEncoderReranker()
    model = r.model

    assert isinstance(model, _FakeCrossEncoderModel)
    assert r.use_reranker is True
    assert r._initialized is True
    # Second access returns the SAME cached instance, not a fresh reload.
    assert r.model is model


def test_rerank_uses_model_predictions_when_available(monkeypatch):
    _inject_fake_sentence_transformers(monkeypatch, _FakeCrossEncoderModel)

    r = CrossEncoderReranker()
    out = r.rerank("q", _DOCS, top_k=2)

    # alpha/beta/gamma score 0.2/0.8/0.5 respectively -- sorted descending,
    # top_k=2 keeps beta then gamma.
    assert [d["text"] for d, _ in out] == ["beta", "gamma"]
    assert [round(s, 2) for _, s in out] == [0.8, 0.5]


def test_rerank_standalone_call_uses_the_model_without_a_prior_model_access(
    monkeypatch,
):
    # Regression guard: rerank()'s own docstring example calls .rerank() directly
    # with no prior `.model` access -- use_reranker starts False on a fresh
    # instance and only becomes True as a SIDE EFFECT of accessing `.model`, so
    # a check ordered as `not self.use_reranker or not self.model` would
    # short-circuit and never touch `.model` at all, silently falling back even
    # though the cross-encoder is fully available.
    _inject_fake_sentence_transformers(monkeypatch, _FakeCrossEncoderModel)

    r = CrossEncoderReranker()
    out = r.rerank("q", _DOCS, top_k=2)  # no r.model access beforehand

    assert [d["text"] for d, _ in out] == ["beta", "gamma"]


def test_rerank_falls_back_when_model_predict_raises(monkeypatch):
    class _RaisingModel(_FakeCrossEncoderModel):
        def predict(self, pairs):
            raise RuntimeError("inference failed")

    _inject_fake_sentence_transformers(monkeypatch, _RaisingModel)

    r = CrossEncoderReranker()
    out = r.rerank("q", _DOCS, top_k=10)

    # Falls back to original order/scores despite use_reranker=True, since the
    # actual predict() call failed.
    assert [d["text"] for d, _ in out] == ["alpha", "beta", "gamma"]
    assert [s for _, s in out] == [0.1, 0.9, 0.0]
