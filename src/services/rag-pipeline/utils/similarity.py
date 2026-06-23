"""
Similarity Calculation Utilities

Shared vector similarity functions used across multiple components.
Provides cosine similarity calculation with NumPy optimization.

This is a utility module for shared mathematical operations.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

# Optional dependency handling
try:
    import numpy as np

    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    np = None
    logging.warning("NumPy not available. Install with: pip install numpy")


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors

    Cosine similarity measures the cosine of the angle between two vectors,
    ranging from -1 (opposite) to 1 (identical), with 0 indicating orthogonality.

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Cosine similarity in range [-1, 1]

    Raises:
        ValueError: If vectors are invalid or empty

    Example:
        >>> vec1 = [1.0, 2.0, 3.0]
        >>> vec2 = [1.0, 2.0, 3.0]
        >>> similarity = cosine_similarity(vec1, vec2)
        >>> print(f"Similarity: {similarity:.2f}")
        Similarity: 1.00
    """
    if not vec1 or not vec2:
        return 0.0

    if len(vec1) != len(vec2):
        logger.warning(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")
        return 0.0

    try:
        if NUMPY_AVAILABLE:
            # Use NumPy for efficiency
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)

            dot_product = float(np.dot(v1, v2))
            norm1 = float(np.linalg.norm(v1))
            norm2 = float(np.linalg.norm(v2))

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            logger.debug(f"✅ Cosine similarity: {similarity:.4f} (NumPy)")

            return similarity
        else:
            # Pure Python fallback
            dot_product = sum(a * b for a, b in zip(vec1, vec2))
            norm1 = sum(a * a for a in vec1) ** 0.5
            norm2 = sum(b * b for b in vec2) ** 0.5

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            logger.debug(f"✅ Cosine similarity: {similarity:.4f} (Python)")

            return similarity

    except Exception as e:
        logger.warning(f"Cosine similarity calculation failed: {e}")
        return 0.0


def euclidean_distance(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate Euclidean distance between two vectors

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Euclidean distance (non-negative)

    Raises:
        ValueError: If vectors invalid

    Example:
        >>> vec1 = [1.0, 2.0, 3.0]
        >>> vec2 = [1.0, 2.0, 3.0]
        >>> distance = euclidean_distance(vec1, vec2)
        >>> print(f"Distance: {distance:.2f}")
        Distance: 0.00
    """
    if not vec1 or not vec2:
        raise ValueError("Vectors cannot be empty")

    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")

    try:
        if NUMPY_AVAILABLE:
            v1 = np.array(vec1, dtype=np.float32)
            v2 = np.array(vec2, dtype=np.float32)
            distance = float(np.linalg.norm(v1 - v2))

            logger.debug(f"✅ Euclidean distance: {distance:.4f} (NumPy)")

            return distance
        else:
            # Pure Python fallback
            distance = sum((a - b) ** 2 for a, b in zip(vec1, vec2)) ** 0.5

            logger.debug(f"✅ Euclidean distance: {distance:.4f} (Python)")

            return distance

    except Exception as e:
        logger.error(f"Euclidean distance calculation failed: {e}")
        raise


def dot_product(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculate dot product of two vectors

    Args:
        vec1: First vector
        vec2: Second vector

    Returns:
        Dot product (scalar)

    Raises:
        ValueError: If vectors invalid

    Example:
        >>> vec1 = [1.0, 2.0, 3.0]
        >>> vec2 = [4.0, 5.0, 6.0]
        >>> result = dot_product(vec1, vec2)
        >>> print(f"Dot product: {result:.2f}")
        Dot product: 32.00
    """
    if not vec1 or not vec2:
        raise ValueError("Vectors cannot be empty")

    if len(vec1) != len(vec2):
        raise ValueError(f"Vector dimension mismatch: {len(vec1)} vs {len(vec2)}")

    try:
        if NUMPY_AVAILABLE:
            result = float(np.dot(np.array(vec1), np.array(vec2)))
        else:
            result = sum(a * b for a, b in zip(vec1, vec2))

        logger.debug(f"✅ Dot product: {result:.4f}")

        return result

    except Exception as e:
        logger.error(f"Dot product calculation failed: {e}")
        raise
