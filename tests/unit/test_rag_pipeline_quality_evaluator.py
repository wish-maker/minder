"""Unit tests for rag-pipeline/domain/quality_evaluator.AdvancedQualityEvaluator.

The Self-RAG quality evaluator has two layers: optional heavy-model metrics
(sentence-transformers / bert-score) and pure-Python FALLBACKS used whenever those
libs aren't installed. The fallbacks — Jaccard/overlap similarity, precision/recall
F1, the hallucination heuristics, and the length/coherence scorers — are what run in
CI (the heavy libs aren't in the test image) and are pure, deterministic logic worth
locking down. These tests exercise that fallback layer directly, so no models load
and no fakes are needed.

Loaded by-path because the service dir is hyphenated (`rag-pipeline`) and the
one-process conftest can't import it as a package.
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
    / "quality_evaluator.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("rag_quality_evaluator", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_qe = _load()
AdvancedQualityEvaluator = _qe.AdvancedQualityEvaluator


def _ev():
    # No model names matter here — the fallbacks don't touch them.
    return AdvancedQualityEvaluator()


# --- _basic_semantic_similarity (Jaccard + overlap) -------------------------


def test_basic_similarity_identical_text_is_high():
    r = _ev()._basic_semantic_similarity("the cat sat", "the cat sat")
    assert r["similarity"] == 1.0
    assert r["confidence"] == "high"
    assert r["fallback"] == "basic_word_overlap"


def test_basic_similarity_disjoint_text_is_zero_low():
    r = _ev()._basic_semantic_similarity("alpha beta", "gamma delta")
    assert r["similarity"] == 0.0
    assert r["confidence"] == "low"


def test_basic_similarity_empty_context_is_zero():
    r = _ev()._basic_semantic_similarity("anything here", "")
    assert r["similarity"] == 0.0
    assert r["normalized_similarity"] == 0.0
    assert r["confidence"] == "low"


def test_basic_similarity_partial_overlap_between_bounds():
    # answer={a,b,c,d}, context={a,b} -> jaccard 2/4=.5, overlap 2/4=.5 -> .5
    r = _ev()._basic_semantic_similarity("a b c d", "a b")
    assert 0.0 < r["similarity"] < 1.0


# --- _basic_factual_score (precision / recall / F1) -------------------------


def test_basic_factual_perfect_match():
    r = _ev()._basic_factual_score("one two three", "one two three")
    assert r["precision"] == 1.0
    assert r["recall"] == 1.0
    assert r["f1"] == 1.0


def test_basic_factual_precision_recall_asymmetry():
    # answer has an extra word not in reference -> precision < 1, recall == 1
    r = _ev()._basic_factual_score("one two three four", "one two three")
    assert r["precision"] < 1.0
    assert r["recall"] == 1.0
    assert 0.0 < r["f1"] < 1.0


def test_basic_factual_empty_reference_is_zero():
    r = _ev()._basic_factual_score("some answer", "")
    assert r == {
        "precision": 0.0,
        "recall": 0.0,
        "f1": 0.0,
        "confidence": "low",
        "fallback": "basic_word_overlap",
    }


# --- evaluate_hallucination (pure heuristics) -------------------------------


def test_hallucination_short_answer_flagged():
    r = _ev().evaluate_hallucination("Too short.", "context text here")
    assert "very_short_answer" in r["indicators"]
    assert r["hallucination_score"] > 0


def test_hallucination_uncertainty_markers_flagged():
    answer = "It might be possibly true, but I am not sure and it is uncertain."
    r = _ev().evaluate_hallucination(answer, answer)
    assert any("uncertainty_markers" in i for i in r["indicators"])


def test_hallucination_score_capped_at_one():
    # Pile on every indicator: short + markers + generic + no factual verbs.
    answer = "maybe ??? typically usually"
    r = _ev().evaluate_hallucination(answer, "unrelated context")
    assert r["hallucination_score"] <= 1.0
    assert r["is_hallucination"] is True
    assert r["confidence"] == "low"


def test_hallucination_good_factual_answer_low_score():
    # A long, factual, on-topic answer over matching context -> not a hallucination.
    context = "Paris is the capital of France and has a population of two million."
    answer = (
        "Paris is the capital of France. It is a large city and it has a "
        "population of about two million people living there."
    )
    r = _ev().evaluate_hallucination(answer, context)
    assert r["is_hallucination"] is False
    assert r["confidence"] == "high"


# --- _evaluate_length thresholds --------------------------------------------


def test_length_scoring_thresholds():
    ev = _ev()
    assert ev._evaluate_length("x" * 10) == 0.3  # < 50 too short
    assert ev._evaluate_length("x" * 100) == 0.8  # 50..200 good
    assert ev._evaluate_length("x" * 300) == 1.0  # >= 200 excellent


# --- _evaluate_coherence penalties ------------------------------------------


def test_coherence_default_good():
    assert _ev()._evaluate_coherence("A clean complete sentence.") == 0.8


def test_coherence_penalises_ellipsis_and_stays_floored():
    ev = _ev()
    # "..." (-0.3) off a 0.8 base (the "..." also counts as a terminator, so no
    # extra no-terminator penalty).
    assert ev._evaluate_coherence("incomplete thought ...") == pytest.approx(0.5)
    # Stack every compatible penalty: "..."(-0.3) + "unknown"(-0.2) + >3 '?'(-0.2)
    # off 0.8 -> 0.1, and the max(0.0, ...) floor keeps it non-negative.
    score = ev._evaluate_coherence("well ... ??? ?? unknown thing")
    assert 0.0 <= score < 0.2


def test_coherence_penalises_missing_terminator():
    ev = _ev()
    assert ev._evaluate_coherence(
        "no ending punctuation here"
    ) < ev._evaluate_coherence("has an ending.")


# --- evaluate_answer_quality (combined, fallback path) ----------------------


def test_answer_quality_combined_in_range_and_flags():
    context = "Paris is the capital of France with about two million residents."
    answer = (
        "Paris is the capital of France and it has a population of around two "
        "million residents in the city."
    )
    r = _ev().evaluate_answer_quality("What is Paris?", answer, context)
    assert 0.0 <= r["overall_quality"] <= 1.0
    assert r["confidence"] in {"high", "medium", "low"}
    assert isinstance(r["is_high_quality"], bool)
    assert r["is_high_quality"] == (r["overall_quality"] > 0.7)
    # fallback layer was used (no heavy models in the test env)
    assert r["semantic"].get("fallback") == "basic_word_overlap"
    assert r["factual"].get("fallback") == "basic_word_overlap"


def test_answer_quality_poor_answer_scores_low():
    r = _ev().evaluate_answer_quality(
        "Explain photosynthesis.",
        "maybe ???",
        "Photosynthesis converts light to energy.",
    )
    assert r["is_high_quality"] is False


# --- semantic_model / evaluate_semantic_similarity (real-model path) -------


class _FakeSentenceTransformer:
    def __init__(self, model_name):
        self.model_name = model_name

    def encode(self, text):
        return text


def _fake_cos_sim(a, b):
    def sim(x, y):
        return 1.0 if x == y else 0.3

    if isinstance(b, list):
        return [[sim(a, item) for item in b]]
    return [[sim(a, b)]]


def _with_fake_sentence_transformers(monkeypatch):
    monkeypatch.setattr(_qe, "SENTENCE_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(
        _qe, "SentenceTransformer", _FakeSentenceTransformer, raising=False
    )
    monkeypatch.setattr(_qe, "cos_sim", _fake_cos_sim, raising=False)


def test_semantic_model_property_loads_and_caches(monkeypatch):
    _with_fake_sentence_transformers(monkeypatch)
    ev = _ev()

    model = ev.semantic_model

    assert isinstance(model, _FakeSentenceTransformer)
    assert ev.semantic_model is model  # cached, not reloaded


def test_semantic_model_property_falls_back_to_false_on_load_exception(monkeypatch):
    monkeypatch.setattr(_qe, "SENTENCE_TRANSFORMERS_AVAILABLE", True)

    def _boom(model_name):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(_qe, "SentenceTransformer", _boom, raising=False)
    ev = _ev()

    assert ev.semantic_model is False
    # Cached as False -- a second access must not retry the failing load.
    assert ev.semantic_model is False


def test_evaluate_semantic_similarity_uses_real_model_when_available(monkeypatch):
    _with_fake_sentence_transformers(monkeypatch)
    ev = _ev()

    result = ev.evaluate_semantic_similarity("the answer", "the answer")

    assert result["similarity"] == 1.0
    assert result["confidence"] == "high"
    assert "fallback" not in result


def test_evaluate_semantic_similarity_checks_max_source_similarity(monkeypatch):
    _with_fake_sentence_transformers(monkeypatch)
    ev = _ev()
    sources = [{"text": "unrelated"}, {"text": "the answer"}, {"text": ""}]

    result = ev.evaluate_semantic_similarity("the answer", "different context", sources)

    # The "the answer" source matches exactly -> max source similarity is 1.0,
    # even though the raw context similarity is only the "not equal" 0.3.
    assert result["similarity"] == 0.3
    assert result["max_source_similarity"] == 1.0


def test_evaluate_semantic_similarity_falls_back_on_model_exception(monkeypatch):
    monkeypatch.setattr(_qe, "SENTENCE_TRANSFORMERS_AVAILABLE", True)
    monkeypatch.setattr(
        _qe, "SentenceTransformer", _FakeSentenceTransformer, raising=False
    )

    def _boom(a, b):
        raise RuntimeError("cos_sim blew up")

    monkeypatch.setattr(_qe, "cos_sim", _boom, raising=False)
    ev = _ev()

    result = ev.evaluate_semantic_similarity("a b c", "a b")

    assert result["fallback"] == "basic_word_overlap"


# --- bertscore_model / evaluate_bertscore (real-model path) -----------------


class _FakeTensor:
    """Duck-types just enough of a single-element torch tensor: real BERTScore
    compares the whole (1-example) tensor directly against a float (`F1 >
    0.85`), not `F1[0] > 0.85` -- a plain list/float stand-in can't support
    that comparison the way this code calls it."""

    def __init__(self, value):
        self._value = value

    def __getitem__(self, idx):
        return self._value

    def __float__(self):
        return float(self._value)

    def __gt__(self, other):
        return self._value > other


class _FakeBERTScorer:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def score(self, cands, refs, batch_size=1, verbose=False):
        return _FakeTensor(0.9), _FakeTensor(0.8), _FakeTensor(0.85)


def _with_fake_bertscore(monkeypatch, scorer_cls=_FakeBERTScorer):
    monkeypatch.setattr(_qe, "BERTSCORE_AVAILABLE", True)
    monkeypatch.setattr(_qe, "BERTScorer", scorer_cls, raising=False)


def test_bertscore_model_property_loads_and_caches(monkeypatch):
    _with_fake_bertscore(monkeypatch)
    ev = _ev()

    model = ev.bertscore_model

    assert isinstance(model, _FakeBERTScorer)
    assert ev.bertscore_model is model


def test_bertscore_model_property_falls_back_to_false_on_load_exception(monkeypatch):
    monkeypatch.setattr(_qe, "BERTSCORE_AVAILABLE", True)

    def _boom(**kwargs):
        raise RuntimeError("model download failed")

    monkeypatch.setattr(_qe, "BERTScorer", _boom, raising=False)
    ev = _ev()

    assert ev.bertscore_model is False
    assert ev.bertscore_model is False


def test_evaluate_bertscore_uses_real_model_when_available(monkeypatch):
    _with_fake_bertscore(monkeypatch)
    ev = _ev()

    result = ev.evaluate_bertscore("the answer", "the reference")

    assert result["precision"] == 0.9
    assert result["recall"] == 0.8
    assert result["f1"] == 0.85
    assert result["confidence"] == "medium"
    assert "fallback" not in result


def test_evaluate_bertscore_falls_back_on_model_exception(monkeypatch):
    class _RaisingScorer(_FakeBERTScorer):
        def score(self, *a, **k):
            raise RuntimeError("scoring blew up")

    _with_fake_bertscore(monkeypatch, _RaisingScorer)
    ev = _ev()

    result = ev.evaluate_bertscore("the answer", "the reference")

    assert result["fallback"] == "basic_word_overlap"


# --- exception handlers ------------------------------------------------------


def test_hallucination_detection_exception_returns_medium_confidence_default(
    monkeypatch,
):
    ev = _ev()

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ev, "evaluate_semantic_similarity", _boom)

    result = ev.evaluate_hallucination("some answer here", "some context")

    assert result == {
        "hallucination_score": 0.5,
        "indicators": [],
        "is_hallucination": False,
        "confidence": "medium",
        "error": "boom",
    }


def test_answer_quality_uses_explicit_reference_for_factual_check():
    ev = _ev()

    result = ev.evaluate_answer_quality(
        "question",
        "the exact reference text",
        "totally unrelated context",
        reference="the exact reference text",
    )

    assert result["factual"]["precision"] == 1.0
    assert result["factual"]["recall"] == 1.0


def test_answer_quality_exception_returns_low_confidence_default(monkeypatch):
    ev = _ev()

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ev, "evaluate_semantic_similarity", _boom)

    result = ev.evaluate_answer_quality("q", "answer", "context")

    assert result == {
        "overall_quality": 0.5,
        "error": "boom",
        "confidence": "low",
        "is_high_quality": False,
    }


# --- singleton --------------------------------------------------------------


def test_get_advanced_evaluator_is_singleton():
    a = _qe.get_advanced_evaluator()
    b = _qe.get_advanced_evaluator()
    assert a is b
