"""
HyDE Query Expander

Implements Hypothetical Document Embeddings (HyDE) query expansion.
Generates hypothetical answers to improve retrieval precision.

This is a domain component with NO external dependencies on infrastructure.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class HyDEQueryExpander:
    """
    HyDE query expansion using hypothetical document generation (RPi 4 optimized)

    Improves retrieval precision by:
    1. Generating hypothetical answer to query
    2. Embedding hypothetical answer
    3. Using hypothetical embedding for search

    This approach works better than raw query embeddings because the
    hypothetical answer is closer in semantic space to relevant documents.

    Features:
    - Hypothetical answer generation
    - Embedding generation for hypothetical text
    - Graceful fallback if generation fails
    - Configurable enable/disable

    Attributes:
        _enabled (bool): Whether HyDE expansion is enabled

    Example:
        >>> expander = HyDEQueryExpander()
        >>> result = await expander.expand_query(
        ...     query="What is RAG?",
        ...     llm_manager=manager,
        ...     model="llama3"
        ... )
        >>> if result['expanded']:
        ...     embedding = result['hypothetical_embedding']
    """

    def __init__(self):
        """Initialize HyDE query expander"""
        self._enabled = True

        logger.info("✅ HyDEQueryExpander initialized")

    async def generate_hypothetical_answer(
        self, query: str, llm_manager: Any, model: str = "llama3"
    ) -> str:
        """
        Generate hypothetical answer to query

        Generates a comprehensive answer to the query without external
        context. This hypothetical answer is then embedded for search.

        Args:
            query: User query
            llm_manager: LLM manager for generation
            model: LLM model name

        Returns:
            Generated hypothetical answer text

        Raises:
            ValueError: If query empty
        """
        if not query:
            raise ValueError("query cannot be empty")

        try:
            prompt = f"Please write a comprehensive answer to the following question: {query}"

            # Generate hypothetical answer with higher temperature for creativity
            result = await llm_manager.generate_response(
                prompt=prompt, model=model, temperature=0.7
            )

            hypothetical_answer = result.get("text", "")

            logger.info(
                f"✅ Generated hypothetical answer ({len(hypothetical_answer)} chars)"
            )

            return hypothetical_answer

        except Exception as e:
            logger.warning(f"⚠️ Failed to generate hypothetical answer: {e}")
            return ""

    async def expand_query(
        self,
        query: str,
        llm_manager: Any,
        model: str = "llama3",
        query_embedding: List[float] = None,
    ) -> Dict[str, Any]:
        """
        Expand query using HyDE technique

        Generates hypothetical answer and creates embedding for improved
        semantic search.

        Args:
            query: Original user query
            llm_manager: LLM manager for generation and embedding
            model: LLM model name
            query_embedding: Original query embedding (optional)

        Returns:
            Dict with keys:
                expanded (bool): Whether expansion succeeded
                hypothetical_answer (str): Generated hypothetical text
                hypothetical_embedding (List[float]): Embedding of hypothetical text
                original_query (str): Original query
                original_embedding (List[float]): Original query embedding
                reason (str): Failure reason if expanded=False

        Raises:
            ValueError: If query empty
        """
        if not query:
            raise ValueError("query cannot be empty")

        if not self._enabled:
            logger.debug("HyDE expansion disabled")
            return {"expanded": False, "reason": "HyDE disabled"}

        logger.info(f"🔄 Expanding query with HyDE: {query[:50]}...")

        # Generate hypothetical answer
        hypothetical_answer = await self.generate_hypothetical_answer(
            query, llm_manager, model
        )

        if not hypothetical_answer:
            logger.warning("Failed to generate hypothetical answer")
            return {
                "expanded": False,
                "reason": "Failed to generate hypothetical answer",
            }

        # Generate embedding for hypothetical answer
        try:
            hypothetical_embeddings = await llm_manager.generate_embeddings(
                [hypothetical_answer], model=model
            )
            hypothetical_embedding = hypothetical_embeddings[0]

            logger.info("✅ HyDE query expansion completed")

            return {
                "expanded": True,
                "hypothetical_answer": hypothetical_answer,
                "hypothetical_embedding": hypothetical_embedding,
                "original_query": query,
                "original_embedding": query_embedding,
            }

        except Exception as e:
            logger.warning(f"⚠️ Failed to generate hypothetical embedding: {e}")
            return {
                "expanded": False,
                "reason": "Failed to generate hypothetical embedding",
            }
