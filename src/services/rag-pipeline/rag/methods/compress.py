"""Contextual compression of retrieved context before generation.

Thin wrapper over ``domain.compressors.ContextualCompressor`` (pure-Python
sentence-relevance extraction — no heavy deps, Pi-safe). Shrinks the combined context
to the query-relevant sentences, which cuts prompt size / generation latency on
constrained hardware. Never raises — returns the original context_result on failure.
"""

import logging

logger = logging.getLogger(__name__)


def apply(question, context_result, compressor):
    """Return (context_result, details). details["compressor"] has the size delta."""
    sources = context_result.get("sources", [])
    if compressor is None or not sources:
        return context_result, {}
    try:
        result = compressor.compress(question, sources)
        compressed = result.get("compressed_context")
        if not compressed:
            return context_result, {}
        details = {
            "compressor": {
                "original_length": result.get("original_length"),
                "compressed_length": result.get("compressed_length"),
            }
        }
        return {**context_result, "context": compressed}, details
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ Compression step failed, using full context: {e}")
        return context_result, {}
