"""Decision-engine routing for ``method=auto``.

Wraps ``agent.decision_engine.AgentDecisionEngine``: analyse the query and decide the
pipeline. Returns ``(use_hyde, use_self_rag, details)`` where ``details`` now carries
the *full* decision (retrieval_strategy, top_k, use_reranking, …) so the runner can
apply the parts it controls instead of discarding all but HyDE/Self-RAG (#139).
On any failure returns ``(False, False, {})`` → the runner uses standard retrieval.
"""

import logging

logger = logging.getLogger(__name__)


async def route(question, engine):
    """Return (use_hyde: bool, use_self_rag: bool, details: dict).

    ``details`` includes the engine's ``retrieval_strategy``/``top_k``/``use_reranking``/
    ``use_query_expansion`` so the runner can honour the applicable ones.
    """
    if engine is None:
        return False, False, {}
    try:
        analysis = await engine.analyze_query(question)
        decision = await engine.decide_pipeline(analysis)
        use_hyde = bool(getattr(decision, "use_hyde", False))
        use_self_rag = bool(getattr(decision, "use_self_rag", False))
        strategy = getattr(decision, "retrieval_strategy", None)
        details = {
            "complexity": getattr(
                analysis.complexity, "value", str(analysis.complexity)
            ),
            "intent": analysis.intent,
            "use_hyde": use_hyde,
            "use_self_rag": use_self_rag,
            "retrieval_strategy": (
                getattr(strategy, "value", str(strategy))
                if strategy is not None
                else None
            ),
            "top_k": getattr(decision, "top_k", None),
            "use_reranking": bool(getattr(decision, "use_reranking", False)),
            "use_query_expansion": bool(
                getattr(decision, "use_query_expansion", False)
            ),
        }
        return use_hyde, use_self_rag, details
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Decision engine failed, falling back to standard: {e}")
        return False, False, {}
