"""
Contextual Compressor

Compresses retrieved context while preserving query-relevant information.
Uses sentence-level relevance scoring to maintain important content.

This is a domain component with NO external dependencies.
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ContextualCompressor:
    """
    Compress retrieved context while preserving relevance (RPi 4 optimized)

    Reduces context size by extracting query-relevant sentences while
    maintaining information critical to answering the query.

    Features:
    - Sentence-level relevance scoring
    - Query-word overlap detection
    - Token-aware length limits
    - Preserves sentence structure

    Attributes:
        max_tokens (int): Maximum tokens in compressed context
        compression_ratio (float): Target compression ratio (0.0-1.0)
        avg_chars_per_token (int): Average characters per token

    Example:
        >>> compressor = ContextualCompressor(max_tokens=2000)
        >>> result = compressor.compress(query, retrieved_docs)
        >>> print(f"Compressed {result['original_length']} → {result['compressed_length']} chars")
    """

    def __init__(
        self,
        max_tokens: int = 2000,
        compression_ratio: float = 0.3
    ):
        """
        Initialize contextual compressor

        Args:
            max_tokens: Maximum tokens in compressed output
            compression_ratio: Target compression ratio (0.3 = 30% of original)

        Raises:
            ValueError: If parameters invalid
        """
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")

        if not 0 < compression_ratio <= 1:
            raise ValueError(f"compression_ratio must be in (0, 1], got {compression_ratio}")

        self.max_tokens = max_tokens
        self.compression_ratio = compression_ratio
        self.avg_chars_per_token = 4  # Approximate for English

        logger.info(f"✅ ContextualCompressor initialized: max_tokens={max_tokens}, ratio={compression_ratio}")

    def compress(
        self,
        query: str,
        contexts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compress context while preserving relevance

        Extracts sentences with highest query-word overlap to maintain
        relevant information while reducing size.

        Args:
            query: Query string for relevance scoring
            contexts: List of context dicts with 'text' field

        Returns:
            Dict with keys:
                compressed_context (str): Compressed text
                original_length (int): Original character count
                compressed_length (int): Compressed character count

        Raises:
            ValueError: If query empty
        """
        if not query:
            raise ValueError("query cannot be empty")

        if not contexts:
            logger.debug("No contexts to compress")
            return {
                "compressed_context": "",
                "original_length": 0,
                "compressed_length": 0
            }

        # Combine all contexts
        original_text = "\n\n".join([ctx.get("text", "") for ctx in contexts])
        original_length = len(original_text)

        # Calculate target length
        target_length = int(original_length * self.compression_ratio)

        # Extract key sentences based on query relevance
        compressed = self._extract_key_sentences(query, original_text, target_length)

        # Ensure we don't exceed max tokens
        max_chars = self.max_tokens * self.avg_chars_per_token
        if len(compressed) > max_chars:
            compressed = compressed[:max_chars] + "..."
            logger.debug(f"Truncated compressed context to {max_chars} chars")

        compressed_length = len(compressed)

        logger.debug(
            f"Compressed context: {original_length} → {compressed_length} chars "
            f"({100 * compressed_length / original_length:.1f}%)"
        )

        return {
            "compressed_context": compressed,
            "original_length": original_length,
            "compressed_length": compressed_length,
        }

    def _extract_key_sentences(
        self,
        query: str,
        text: str,
        target_length: int
    ) -> str:
        """
        Extract key sentences based on query relevance

        Scores sentences by query-word overlap and selects top sentences
        until target length is reached.

        Args:
            query: Query string for relevance scoring
            text: Source text to extract from
            target_length: Target character count

        Returns:
            Extracted sentences joined by periods
        """
        # Split into sentences
        sentences = [s.strip() for s in text.split(".") if s.strip()]

        if not sentences:
            logger.debug("No sentences found in text")
            return text[:target_length]

        # Extract query words for relevance scoring
        query_words = set(query.lower().split())

        if not query_words:
            logger.debug("No query words for relevance scoring")
            return text[:target_length]

        # Score sentences by query relevance
        sentence_scores = []

        for sentence in sentences:
            sentence_lower = sentence.lower()
            sentence_words = set(sentence_lower.split())

            # Calculate word overlap ratio
            overlap = len(query_words & sentence_words)
            score = overlap / max(len(query_words), 1)
            sentence_scores.append((sentence, score))

        # Sort by relevance (descending)
        sorted_sentences = sorted(sentence_scores, key=lambda x: x[1], reverse=True)

        # Take top sentences until target length
        compressed_sentences = []
        current_length = 0

        for sentence, score in sorted_sentences:
            next_length = current_length + len(sentence) + 2  # +2 for ". "
            if next_length <= target_length:
                compressed_sentences.append(sentence)
                current_length = next_length
            else:
                break

        result = ". ".join(compressed_sentences) + "." if compressed_sentences else ""

        logger.debug(
            f"Extracted {len(compressed_sentences)}/{len(sentences)} sentences "
            f"({current_length}/{target_length} chars)"
        )

        return result
