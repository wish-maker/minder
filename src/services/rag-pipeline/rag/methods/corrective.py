"""Corrective RAG orchestration.

Thin wrapper over ``domain.pipelines.corrective_rag.CorrectiveRAGPipeline``: grade the
already-retrieved context; if the grade is weak, rewrite the query and re-retrieve.
Returns the (possibly corrected) context_result plus a details dict. Never raises —
on any failure it returns the original context_result so the caller degrades to the
standard path.
"""

import logging

logger = logging.getLogger(__name__)


async def correct(
    question,
    context_result,
    pipeline_obj,
    retrieve,
    pipeline,
    top_k,
    ollama_manager,
    model,
):
    """Return (context_result, details).

    context_result is either the original or a re-retrieved one; details records the
    grade and whether a correction fired. ``pipeline_obj`` is the CorrectiveRAGPipeline
    (None → no-op).
    """
    if pipeline_obj is None:
        return context_result, {}
    try:
        grade = await pipeline_obj.grade_context(
            question, context_result.get("context", ""), ollama_manager, model
        )
        details = {
            "grade": grade.get("grade"),
            "score": grade.get("score"),
            "corrected": False,
        }
        if grade.get("grade") in ("ambiguous", "incorrect"):
            refined = await pipeline_obj.rewrite_query(question, ollama_manager, model)
            if refined:
                new_result = await retrieve(pipeline, refined, top_k)
                if new_result.get("sources"):
                    details["corrected"] = True
                    details["refined_query_chars"] = len(refined)
                    return new_result, details
        return context_result, details
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Corrective RAG failed, using original retrieval: {e}")
        return context_result, {}
