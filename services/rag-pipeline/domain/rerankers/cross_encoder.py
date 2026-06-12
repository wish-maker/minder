"""
Cross-Encoder Re-ranker

Uses cross-encoder models to re-rank retrieved documents for improved precision.
Optimized for Raspberry Pi 4 with CPU-only inference and memory management.

This is a domain component with NO external dependencies on infrastructure.
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """
    Cross-encoder re-ranker for improved retrieval precision (RPi 4 optimized)

    Re-ranks retrieved documents using cross-encoder models that compute
    query-document similarity more accurately than bi-encoders.

    Features:
    - Lazy model loading (only when needed)
    - CPU-only inference (RPi 4 compatible)
    - Graceful fallback if model unavailable
    - Memory-efficient (max_length=512)

    Attributes:
        model_name (str): Cross-encoder model name
        use_reranker (bool): Whether re-ranking is enabled

    Example:
        >>> reranker = CrossEncoderReranker()
        >>> results = reranker.rerank(query, documents, top_k=5)
        >>> for doc, score in results:
        ...     print(f"{score:.2f}: {doc['text'][:50]}...")
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """
        Initialize cross-encoder re-ranker

        Args:
            model_name: HuggingFace model name for cross-encoder

        Note:
            Model is lazy-loaded on first use to avoid startup overhead
        """
        self.model_name = model_name
        self._model = None
        self._initialized = False
        self.use_reranker = False  # Disabled by default for RPi

        logger.info(f"✅ CrossEncoderReranker initialized: {model_name}")

    @property
    def model(self):
        """
        Lazy load cross-encoder model

        Returns:
            CrossEncoder model or False if unavailable

        Note:
            Model loads on first access to avoid startup delay
        """
        if self._model is None and not self._initialized:
            try:
                from sentence_transformers import CrossEncoder

                logger.info(f"🔄 Loading cross-encoder model: {self.model_name}")

                self._model = CrossEncoder(
                    self.model_name,
                    device="cpu",
                    max_length=512  # Reduced for memory efficiency
                )

                self._initialized = True
                self.use_reranker = True
                logger.info("✅ Cross-encoder model loaded (CPU-only)")

            except Exception as e:
                logger.warning(f"⚠️ Failed to load cross-encoder: {e}")
                self._initialized = True
                self._model = False

        return self._model

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Tuple[Dict[str, Any], float]]:
        """
        Re-rank documents using cross-encoder

        Computes query-document similarity scores using cross-encoder
        and returns top-k documents sorted by relevance.

        Args:
            query: Query string
            documents: List of document dicts with 'text' field
            top_k: Number of top results to return

        Returns:
            List of (document, score) tuples sorted by score (descending)

        Raises:
            ValueError: If query or documents invalid
        """
        if not query:
            raise ValueError("query cannot be empty")

        if not documents:
            logger.warning("No documents to re-rank")
            return []

        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")

        # Fallback if model unavailable
        if not self.use_reranker or not self.model:
            logger.debug("Using fallback ranking (original scores)")
            return [(doc, doc.get("score", 0.0)) for doc in documents[:top_k]]

        try:
            # Create query-document pairs
            pairs = [[query, doc.get("text", "")] for doc in documents]

            # Predict cross-encoder scores
            scores = self.model.predict(pairs)

            # Sort by score and return top-k
            reranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
            return reranked[:top_k]

        except Exception as e:
            logger.warning(f"⚠️ Re-ranking failed: {e}")
            # Fallback to original scores
            return [(doc, doc.get("score", 0.0)) for doc in documents[:top_k]]
