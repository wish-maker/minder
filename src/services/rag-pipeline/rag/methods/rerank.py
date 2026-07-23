"""Adaptive re-ranking of retrieved sources.

Capability-adaptive by design: if the cross-encoder is available (sentence-transformers
installed — typically a beefier x86 host), use ``domain.rerankers.CrossEncoderReranker``.
Otherwise (e.g. the Raspberry Pi target, no torch) fall back to a lightweight
LLM-based re-rank that needs no extra dependencies. Either way the sources are
reordered and the context string is rebuilt from the new order.

Never raises — on any failure returns the original context_result unchanged.
"""

import logging
import re

logger = logging.getLogger(__name__)


def _rebuild(context_result, sources):
    context = "\n\n".join(s.get("text", "") for s in sources)
    return {**context_result, "context": context, "sources": sources}


async def _llm_rerank(question, sources, ollama_manager, model):
    """Ask the LLM to order the passages by relevance. Returns reordered sources or None."""
    listing = "\n".join(
        f"[{i}] {s.get('text', '')[:400]}" for i, s in enumerate(sources)
    )
    prompt = (
        "Rank the passages below by how relevant each is to the question, most "
        "relevant first. Return ONLY a comma-separated list of the passage numbers "
        f"(e.g. 2,0,1). There are {len(sources)} passages.\n\n"
        f"Question: {question}\n\nPassages:\n{listing}\n\nRanking:"
    )
    try:
        result = await ollama_manager.generate_response(
            prompt=prompt, context="", model=model, temperature=0.0
        )
        raw = result.get("text") or ""
        order = [int(n) for n in re.findall(r"\d+", raw)]
        # Keep valid, unique indices; append any the model dropped so nothing is lost.
        seen, ordered_idx = set(), []
        for i in order:
            if 0 <= i < len(sources) and i not in seen:
                seen.add(i)
                ordered_idx.append(i)
        for i in range(len(sources)):
            if i not in seen:
                ordered_idx.append(i)
        if not ordered_idx:
            return None
        return [sources[i] for i in ordered_idx]
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ LLM re-rank failed: {e}")
        return None


async def apply(question, context_result, reranker, ollama_manager, model):
    """Return (context_result, details). details["reranker"] ∈ {cross_encoder, llm}."""
    sources = context_result.get("sources", [])
    if not sources or len(sources) < 2:
        return context_result, {}
    try:
        # Prefer the cross-encoder when the optional dep is present. Accessing
        # reranker.model lazily loads it; it returns False if sentence-transformers
        # (torch) is unavailable, in which case we use the LLM fallback instead.
        if reranker is not None and reranker.model:
            reranked = reranker.rerank(question, sources, top_k=len(sources))
            ordered = [doc for doc, _score in reranked]
            return _rebuild(context_result, ordered), {"reranker": "cross_encoder"}

        ordered = await _llm_rerank(question, sources, ollama_manager, model)
        if ordered is not None:
            return _rebuild(context_result, ordered), {"reranker": "llm"}
        return context_result, {}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Re-rank step failed, keeping original order: {e}")
        return context_result, {}
