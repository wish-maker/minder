"""HyDE (Hypothetical Document Embeddings) query rewriting.

Thin wrapper over ``domain.expansion.hyde.HyDEQueryExpander``: generate a hypothetical
answer to the question and use *that* text as the retrieval query. Retrieval then
embeds it with the KB's own embedding model, so we sidestep the expander's internal
"embed with the LLM model" behaviour.
"""

import logging

logger = logging.getLogger(__name__)


async def rewrite_query(question, expander, ollama_manager, model):
    """Return a hypothetical-answer string to retrieve with, or None to fall back.

    Never raises — any failure returns None so the caller uses the raw question.
    """
    if expander is None:
        return None
    try:
        hypothetical = await expander.generate_hypothetical_answer(
            question, ollama_manager, model=model
        )
        return hypothetical or None
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"⚠️ HyDE failed, using raw query: {e}")
        return None
