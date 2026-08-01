"""Unit tests for AgentDecisionEngine's pure heuristics (rag-pipeline/domain/decision_engine).

The LLM paths (analyze_query/decide_pipeline) call Ollama, but their rule-based
FALLBACKS run whenever the LLM is unreachable (common on the Pi) and drive real RAG
behaviour (strategy, top_k, HyDE/Self-RAG toggles). Those + the perf-optimizer and
stats aggregation are deterministic and were untested. Module imports only stdlib
(httpx is imported inside the async methods), so it loads by path.
"""

import importlib.util
import json
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


def _record(strategy, complexity, confidence):
    """A decision_history entry shaped exactly as decide_pipeline stores it —
    analysis/decision via __dict__, so strategy/complexity are raw Enum members."""
    analysis = _analysis(complexity, confidence)
    decision = Engine()._heuristic_decision(analysis)
    decision.retrieval_strategy = strategy
    return {
        "query": analysis.original_query,
        "analysis": analysis.__dict__,
        "decision": decision.__dict__,
    }


def test_stats_distributions_use_enum_values_and_are_json_serializable():
    eng = Engine()
    eng.decision_history = [
        _record(Strategy.BASIC, Complexity.SIMPLE, 0.9),
        _record(Strategy.BASIC, Complexity.SIMPLE, 0.7),
        _record(Strategy.HIERARCHICAL, Complexity.COMPLEX, 0.5),
    ]

    stats = eng.get_decision_stats()

    # #223/#7: keys are the .value strings, not raw Enum objects.
    assert stats["strategy_distribution"] == {"basic": 2, "hierarchical": 1}
    assert stats["complexity_distribution"] == {"simple": 2, "complex": 1}
    assert stats["total_decisions"] == 3
    assert abs(stats["avg_confidence"] - (0.9 + 0.7 + 0.5) / 3) < 1e-9

    # The whole point: it must round-trip through JSON (Enum keys would raise).
    assert json.loads(json.dumps(stats))["strategy_distribution"]["basic"] == 2
