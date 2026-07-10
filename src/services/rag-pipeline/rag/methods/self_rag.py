"""Self-RAG: quality-based iterative refinement generation.

Thin wrapper over ``domain.pipelines.self_rag.SelfRAGPipeline``. Returns the answer
plus a quality dict. If the pipeline is unavailable or errors, returns ``(None, {})``
so the caller falls back to a standard single-pass generation.

NOTE: full refinement requires the quality evaluator (sentence-transformers), which is
not installed by default; without it Self-RAG degrades to a single pass. See #45.
"""

import logging

logger = logging.getLogger(__name__)


async def generate(pipeline, question, context, sources, ollama_manager, model):
    """Return (answer, quality_dict). (None, {}) signals fall back to standard."""
    if pipeline is None:
        return None, {}
    try:
        result = await pipeline.generate_with_self_refinement(
            question=question,
            context=context or "(no context)",
            sources=sources or [],
            llm_manager=ollama_manager,
            model=model,
        )
        return (result.get("answer") or None), result.get("quality", {})
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Self-RAG failed, falling back to standard: {e}")
        return None, {}
