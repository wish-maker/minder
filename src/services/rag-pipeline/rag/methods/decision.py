"""Decision-engine routing for ``method=auto``.

Wraps ``agent.decision_engine.AgentDecisionEngine``: analyse the query and decide
whether to apply HyDE and/or Self-RAG. Returns ``(use_hyde, use_self_rag, details)``.
On any failure returns ``(False, False, {})`` → the runner uses standard retrieval.
"""

import logging

logger = logging.getLogger(__name__)


async def route(question, engine):
    """Return (use_hyde: bool, use_self_rag: bool, details: dict)."""
    if engine is None:
        return False, False, {}
    try:
        analysis = await engine.analyze_query(question)
        decision = await engine.decide_pipeline(analysis)
        use_hyde = bool(getattr(decision, "use_hyde", False))
        use_self_rag = bool(getattr(decision, "use_self_rag", False))
        details = {
            "complexity": getattr(
                analysis.complexity, "value", str(analysis.complexity)
            ),
            "intent": analysis.intent,
            "use_hyde": use_hyde,
            "use_self_rag": use_self_rag,
        }
        return use_hyde, use_self_rag, details
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Decision engine failed, falling back to standard: {e}")
        return False, False, {}
