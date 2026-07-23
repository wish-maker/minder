"""Corrective RAG (CRAG) pipeline.

LLM-graded retrieval correction. Given a question and the retrieved context, an LLM
grades whether the context is sufficient/relevant to answer. When the grade is weak,
the question is rewritten into a more focused search query so the caller can
re-retrieve. Purely LLM-based (uses the ollama manager as grader) — no heavy
dependencies, so it runs on the Raspberry Pi target as well as a beefier host.

This is a domain component: it does NOT retrieve or generate itself. The runner owns
retrieval/generation and calls grade_context() + rewrite_query() around them.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Valid grades, worst → best. AMBIGUOUS/INCORRECT trigger a corrective re-retrieval.
_GRADES = ("incorrect", "ambiguous", "correct")


class CorrectiveRAGPipeline:
    """Grade retrieved context and rewrite the query when it's insufficient."""

    def __init__(self) -> None:
        logger.info("✅ CorrectiveRAGPipeline initialized")

    async def grade_context(
        self, question: str, context: str, llm_manager: Any, model: str
    ) -> Dict[str, Any]:
        """Grade how well ``context`` supports answering ``question``.

        Returns {"grade": "correct"|"ambiguous"|"incorrect", "score": float}. Never
        raises — on any failure returns a neutral "ambiguous" grade so the caller can
        still decide to correct.
        """
        if not context or not context.strip():
            return {"grade": "incorrect", "score": 0.0}

        prompt = (
            "You are grading whether the retrieved context is sufficient and relevant "
            "to answer the user's question. Reply with EXACTLY one word:\n"
            "CORRECT   - the context clearly contains the information to answer.\n"
            "AMBIGUOUS - the context is partially relevant but may be incomplete.\n"
            "INCORRECT - the context is irrelevant or lacks the information.\n\n"
            f"Question: {question}\n\nContext:\n{context}\n\nGrade:"
        )
        try:
            result = await llm_manager.generate_response(
                prompt=prompt, context="", model=model, temperature=0.0
            )
            raw = (result.get("text") or "").strip().lower()
            grade = "ambiguous"
            for g in _GRADES:
                if g in raw:
                    grade = g
                    break
            score = {"incorrect": 0.0, "ambiguous": 0.5, "correct": 1.0}[grade]
            logger.info(f"🔎 CRAG grade: {grade} (raw={raw[:40]!r})")
            return {"grade": grade, "score": score}
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"⚠️ CRAG grading failed, treating as ambiguous: {e}")
            return {"grade": "ambiguous", "score": 0.5}

    async def rewrite_query(self, question: str, llm_manager: Any, model: str) -> str:
        """Rewrite ``question`` into a focused retrieval query. Returns "" on failure."""
        prompt = (
            "Rewrite the user's question into a concise, keyword-focused search query "
            "that would retrieve the most relevant documents. Return ONLY the rewritten "
            "query, no preamble.\n\n"
            f"Question: {question}\n\nSearch query:"
        )
        try:
            result = await llm_manager.generate_response(
                prompt=prompt, context="", model=model, temperature=0.0
            )
            refined = (result.get("text") or "").strip().strip('"')
            # Guard against the model echoing junk or an empty line.
            if refined and len(refined) <= 500:
                return refined
            return ""
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"⚠️ CRAG query rewrite failed: {e}")
            return ""
