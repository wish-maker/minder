"""
Embedding Cache

Simple in-memory cache for embedding vectors with LRU eviction.
Reduces redundant embedding generation for identical text.

This is an infrastructure component for caching layer.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EmbeddingCache:
    """
    Simple in-memory cache for embeddings (Redis-backed in production)

    Caches embedding vectors using text-based hash keys.
    Implements LRU eviction when at capacity.

    Features:
    - MD5-based text hashing
    - LRU eviction policy
    - Cache statistics tracking
    - Configurable max size

    Attributes:
        cache (Dict): Hash -> embedding mapping
        max_size (int): Maximum cache capacity
        hits (int): Cache hit count
        misses (int): Cache miss count

    Example:
        >>> cache = EmbeddingCache(max_size=1000)
        >>> embedding = cache.get("What is RAG?")
        >>> if embedding is None:
        ...     embedding = generate_embedding("What is RAG?")
        ...     cache.set("What is RAG?", embedding)
    """

    def __init__(self, max_size: int = 1000):
        """
        Initialize embedding cache

        Args:
            max_size: Maximum number of cached embeddings

        Raises:
            ValueError: If max_size invalid
        """
        if max_size <= 0:
            raise ValueError(f"max_size must be positive, got {max_size}")

        self.cache: Dict[str, List[float]] = {}
        self.max_size = max_size
        self.hits = 0
        self.misses = 0

        logger.info(f"✅ EmbeddingCache initialized: max_size={max_size}")

    def _hash_text(self, text: str) -> str:
        """
        Create hash for text

        Args:
            text: Text to hash

        Returns:
            MD5 hex digest of text

        Note:
            MD5 is sufficient for cache keys (not security-sensitive)
        """
        return hashlib.md5(text.encode()).hexdigest()

    def get(self, text: str) -> Optional[List[float]]:
        """
        Get cached embedding

        Args:
            text: Text to retrieve embedding for

        Returns:
            Cached embedding vector or None if not found

        Raises:
            ValueError: If text empty
        """
        if not text:
            raise ValueError("text cannot be empty")

        key = self._hash_text(text)

        if key in self.cache:
            self.hits += 1
            logger.debug(f"✅ Cache hit for text hash: {key[:8]}...")
            return self.cache[key]

        self.misses += 1
        logger.debug(f"❌ Cache miss for text hash: {key[:8]}...")
        return None

    def set(self, text: str, embedding: List[float]) -> None:
        """
        Cache embedding

        Args:
            text: Text to cache embedding for
            embedding: Embedding vector to cache

        Raises:
            ValueError: If text empty or embedding invalid
        """
        if not text:
            raise ValueError("text cannot be empty")

        if not embedding:
            raise ValueError("embedding cannot be empty")

        key = self._hash_text(text)

        # Evict oldest entry if at capacity
        if len(self.cache) >= self.max_size:
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            logger.debug(f"🗑️ Evicted cache entry: {oldest_key[:8]}...")

        self.cache[key] = embedding
        logger.debug(f"💾 Cached embedding: {key[:8]}...")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics

        Returns:
            Dict with keys:
                size (int): Current cache size
                hits (int): Total cache hits
                misses (int): Total cache misses
                hit_rate (float): Cache hit rate (0.0-1.0)
        """
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0

        stats = {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
        }

        logger.debug(
            f"📊 Cache stats: {stats['size']} entries, "
            f"{stats['hit_rate']:.1%} hit rate"
        )

        return stats

    def clear(self) -> None:
        """
        Clear all cached embeddings

        Note:
            Resets hit/miss counters to zero
        """
        self.cache.clear()
        self.hits = 0
        self.misses = 0
        logger.info("🗑️ Cache cleared")
