"""
Hybrid Search Retriever

Combines semantic (dense vector) and BM25 (sparse keyword) retrieval
for improved recall. Uses weighted combination of both methods.

This is a domain component with NO external dependencies.
"""

import logging
import re
from typing import Any, Dict, List, Tuple

# Optional dependency for BM25
try:
    from rank_bm25 import BM25Okapi

    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False
    logging.warning("rank_bm25 not available. Install with: pip install rank-bm25")

# Optional dependency for numerical operations
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logging.warning("NumPy not available. Some optimizations will be disabled.")

logger = logging.getLogger(__name__)


class HybridSearchRetriever:
    """
    Hybrid search retriever combining semantic and BM25 retrieval

    Uses weighted combination of:
    - Dense retrieval: Vector similarity search (typically from Qdrant)
    - Sparse retrieval: BM25 keyword-based search

    Attributes:
        alpha (float): Weight for dense retrieval (0-1). Default 0.5 (equal weight)
        sparse_index (Dict): BM25 index per knowledge base
        documents (Dict): Document text per knowledge base

    Example:
        >>> retriever = HybridSearchRetriever(alpha=0.6)  # Favor dense search
        >>> retriever.index_documents("kb_123", documents)
        >>> results = await retriever.hybrid_search("kb_123", query_emb, "query", dense_results, top_k=5)
    """

    def __init__(self, alpha: float = 0.5):
        """
        Initialize hybrid search retriever

        Args:
            alpha: Weight for dense retrieval [0, 1].
                   0.0 = sparse only, 1.0 = dense only, 0.5 = equal weight

        Raises:
            ValueError: If alpha not in [0, 1]
        """
        if not 0 <= alpha <= 1:
            raise ValueError(f"alpha must be in [0, 1], got {alpha}")

        self.alpha = alpha
        self.sparse_index: Dict[str, Any] = {}  # kb_id -> BM25 index
        self.documents: Dict[str, List[Dict]] = {}  # kb_id -> documents

        logger.info(f"✅ HybridSearchRetriever initialized: alpha={alpha}")

    def index_documents(self, kb_id: str, documents: List[Dict[str, Any]]) -> None:
        """
        Build BM25 sparse index for documents

        Args:
            kb_id: Knowledge base identifier
            documents: List of documents with 'text' field

        Raises:
            ValueError: If kb_id or documents invalid
            RuntimeError: If BM25 not available
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        if not documents:
            logger.warning(f"No documents to index for KB {kb_id}")
            return

        if not BM25_AVAILABLE:
            raise RuntimeError("BM25 not available. Install: pip install rank-bm25")

        try:
            # Tokenize documents
            corpus = []
            for doc in documents:
                text = doc.get("text", "")
                tokens = re.findall(r"\w+", text.lower())
                corpus.append(tokens)

            if not corpus:
                logger.warning(
                    f"No valid tokens extracted from {len(documents)} documents"
                )
                return

            # Build BM25 index
            self.sparse_index[kb_id] = BM25Okapi(corpus)
            self.documents[kb_id] = documents

            logger.info(
                f"✅ BM25 index built for KB {kb_id}: {len(documents)} docs, {len(corpus)} tokens"
            )

        except Exception as e:
            logger.error(f"Failed to build BM25 index for KB {kb_id}: {e}")
            raise

    async def hybrid_search(
        self,
        kb_id: str,
        query_embedding: List[float],
        query: str,
        dense_results: List[Any],
        top_k: int = 5,
    ) -> List[Tuple[Any, float]]:
        """
        Perform hybrid search combining dense and sparse scores

        Args:
            kb_id: Knowledge base identifier
            query_embedding: Query embedding vector (not used here, for interface consistency)
            query: Query string for BM25 search
            dense_results: List of dense retrieval results (with payload and score)
            top_k: Number of results to return

        Returns:
            List of (doc_id, hybrid_score) tuples sorted by score (descending)

        Raises:
            ValueError: If kb_id invalid or top_k <= 0
        """
        if not kb_id:
            raise ValueError("kb_id cannot be empty")

        if top_k <= 0:
            raise ValueError(f"top_k must be positive, got {top_k}")

        if not dense_results:
            logger.warning("No dense results provided for hybrid search")
            return []

        try:
            # Extract dense scores
            dense_scores = {
                r.payload.get("_id", str(r.id)): r.score
                for r in dense_results[: top_k * 2]  # Get more for better combination
            }

            # Perform sparse search
            sparse_results = self._sparse_search(kb_id, query, top_k * 2)

            # Combine scores with weighted average
            hybrid_scores = {}

            # Start with dense contribution
            for doc_id, score in dense_scores.items():
                hybrid_scores[doc_id] = self.alpha * self._normalize_score(
                    score, dense_scores
                )

            # Add sparse contribution
            for doc_id, score in sparse_results.items():
                if doc_id in hybrid_scores:
                    # Already has dense score, add sparse
                    hybrid_scores[doc_id] += (1 - self.alpha) * self._normalize_score(
                        score, sparse_results
                    )
                else:
                    # Only sparse score found
                    hybrid_scores[doc_id] = (1 - self.alpha) * self._normalize_score(
                        score, sparse_results
                    )

            # Sort and return top-k
            sorted_results = sorted(
                hybrid_scores.items(), key=lambda x: x[1], reverse=True
            )
            results = [(doc_id, score) for doc_id, score in sorted_results[:top_k]]

            logger.debug(
                f"Hybrid search: {len(results)} results (dense: {len(dense_scores)}, sparse: {len(sparse_results)})"
            )
            return results

        except Exception as e:
            logger.error(f"Hybrid search failed for KB {kb_id}: {e}")
            # Fallback to dense-only
            return [
                (r.payload.get("_id", str(r.id)), r.score)
                for r in dense_results[:top_k]
            ]

    def _sparse_search(self, kb_id: str, query: str, k: int) -> Dict[str, float]:
        """
        Perform sparse search using BM25

        Args:
            kb_id: Knowledge base identifier
            query: Query string
            k: Number of results to return

        Returns:
            Dictionary of doc_id -> score

        Raises:
            ValueError: If kb_id not indexed
        """
        if kb_id not in self.sparse_index:
            logger.warning(f"No BM25 index found for KB {kb_id}")
            return {}

        try:
            # Tokenize query
            query_tokens = re.findall(r"\w+", query.lower())

            if not query_tokens:
                logger.debug("No query tokens extracted")
                return {}

            # Get BM25 scores
            scores = self.sparse_index[kb_id].get_scores(query_tokens)

            # Find top-k indices
            if NUMPY_AVAILABLE:
                top_indices = np.argsort(scores)[::-1][:k]
            else:
                # Python fallback
                top_indices = sorted(
                    range(len(scores)), key=lambda i: scores[i], reverse=True
                )[:k]

            # Map to document IDs
            doc_scores = {}
            documents = self.documents.get(kb_id, [])

            for idx in top_indices:
                if idx < len(documents):
                    doc = documents[idx]
                    doc_id = doc.get("_id", f"doc_{idx}")
                    doc_scores[doc_id] = (
                        float(scores[idx]) if idx < len(scores) else 0.0
                    )

            logger.debug(f"BM25 search: {len(doc_scores)} results from {k} requested")
            return doc_scores

        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return {}

    def _normalize_score(self, score: float, scores: Dict[str, float]) -> float:
        """
        Normalize score to [0, 1] range

        Args:
            score: Score to normalize
            scores: Reference scores for normalization

        Returns:
            Normalized score in [0, 1]
        """
        if not scores:
            return 0.0

        max_score = max(scores.values()) if scores else 1.0

        if max_score == 0:
            return 0.0

        return score / max_score
