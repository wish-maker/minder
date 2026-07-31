"""Unit tests for AgentDecisionEngine's pure heuristics (rag-pipeline/domain/decision_engine).

The LLM paths (analyze_query/decide_pipeline) call Ollama, but their rule-based
FALLBACKS run whenever the LLM is unreachable (common on the Pi) and drive real RAG
behaviour (strategy, top_k, HyDE/Self-RAG toggles). Those + the perf-optimizer and
stats aggregation are deterministic and were untested. Module imports only stdlib
(httpx is imported inside the async methods), so it loads by path.
"""

import importlib.util
from pathlib import Path

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "rag-pipeline"
    / "domain"
    / "decision_engine.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("decision_engine_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


de = _load()
Engine = de.AgentDecisionEngine
Complexity = de.QueryComplexity
Strategy = de.RetrievalStrategy


# ── _fallback_analysis: word-count → complexity, keyword extraction ──────────
def test_fallback_simple_query():
    a = Engine()._fallback_analysis("what is rag")  # 3 words
    assert a.complexity is Complexity.SIMPLE


def test_fallback_moderate_query():
    a = Engine()._fallback_analysis("how does the retrieval pipeline rank results")  # 7
    assert a.complexity is Complexity.MODERATE


def test_fallback_complex_query_and_keywords():
    q = "explain how the hybrid retrieval strategy improves multi hop reasoning accuracy"
    a = Engine()._fallback_analysis(q)  # >=10 words
    assert a.complexity is Complexity.COMPLEX
    # keywords are the >4-char words, lowercased
    assert "retrieval" in a.keywords and "reasoning" in a.keywords
    assert "how" not in a.keywords  # short words dropped


# ── _heuristic_decision: complexity + confidence → config ────────────────────
def _analysis(complexity, confidence=0.8):
    return de.QueryAnalysis(
        original_query="q",
        complexity=complexity,
        keywords=[],
        entities=[],
        intent="factual",
        confidence=confidence,
    )


def test_heuristic_simple_downshifts():
    d = Engine()._heuristic_decision(_analysis(Complexity.SIMPLE))
    assert d.retrieval_strategy is Strategy.BASIC
    assert d.top_k == 5 and d.use_reranking is False


def test_heuristic_complex_upshifts():
    d = Engine()._heuristic_decision(_analysis(Complexity.COMPLEX))
    assert d.retrieval_strategy is Strategy.HIERARCHICAL
    assert d.top_k == 15 and d.use_query_expansion and d.reasoning_required


def test_heuristic_ambiguous_enables_hyde():
    d = Engine()._heuristic_decision(_analysis(Complexity.AMBIGUOUS))
    assert d.use_hyde and d.top_k == 12


def test_heuristic_low_confidence_enables_self_rag_and_bumps_top_k():
    # MODERATE base top_k=10, +5 for low confidence self-rag.
    d = Engine()._heuristic_decision(_analysis(Complexity.MODERATE, confidence=0.3))
    assert d.use_self_rag and d.top_k == 15


# ── optimize_pipeline: perf feedback → top_k adjustments ─────────────────────
async def test_optimize_reduces_top_k_when_fast_and_good():
    base = Engine()._heuristic_decision(_analysis(Complexity.MODERATE))  # top_k=10
    opt = await Engine().optimize_pipeline(
        base, {"retrieval_latency": 3.0, "answer_relevance": 0.9}
    )
    assert opt.top_k == 8


async def test_optimize_boosts_retrieval_when_low_relevance():
    base = Engine()._heuristic_decision(_analysis(Complexity.MODERATE))  # top_k=10
    opt = await Engine().optimize_pipeline(
        base, {"retrieval_latency": 1.0, "answer_relevance": 0.4}
    )
    assert opt.top_k == 13 and opt.use_reranking and opt.use_query_expansion


# ── get_decision_stats ───────────────────────────────────────────────────────
def test_stats_empty():
    assert Engine().get_decision_stats() == {"total_decisions": 0}


# NOTE: the non-empty get_decision_stats path is intentionally NOT asserted here.
# It keys strategy/complexity distributions by the raw Enum objects (from
# decision.__dict__), not their .value, so the result is not JSON-serializable.
# The method is currently uncalled (no endpoint/consumer), so it's a latent defect
# rather than an active bug — recorded in the standardization tracking issue rather
# than locked in as "correct" behavior here.
