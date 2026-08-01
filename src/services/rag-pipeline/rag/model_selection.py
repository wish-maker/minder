"""Generation-model resolution for RAG queries (pure, stdlib-only → unit-testable).

Kept out of routes/rag.py (which pulls qdrant/ollama/domain at import) so the
precedence logic can be tested by-path without those heavy deps.
"""

from typing import Dict, Optional


def resolve_llm_model(
    query_model: Optional[str],
    pipeline: Dict,
    knowledge_bases: Dict,
    default: str,
) -> str:
    """Pick the generation model, most-specific first: an explicit per-query override
    → the pipeline's own setting → the first referenced KB's configured ``llm_model``
    → the platform default.

    The KB's ``llm_model`` is a stored, user-set field, but the query path used to read
    it only off the pipeline (which never captured it) and so ALWAYS fell back to the
    default — a KB configured for a stronger model was silently ignored. This mirrors
    how the embedding model is already resolved from the KB. (Embeddings are NOT
    overridable per query — they must match the model used at ingest time.)
    """
    kb_ids = pipeline.get("knowledge_base_ids") or []
    first_kb = knowledge_bases.get(kb_ids[0], {}) if kb_ids else {}
    return (
        query_model or pipeline.get("llm_model") or first_kb.get("llm_model") or default
    )
