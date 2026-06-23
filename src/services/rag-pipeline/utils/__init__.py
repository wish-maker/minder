"""
Utils Package

This package contains shared utility functions used across
multiple components to eliminate code duplication.
"""

from .chunking import chunk_text, chunk_text_fallback
from .similarity import cosine_similarity, dot_product, euclidean_distance

__all__ = [
    "chunk_text",
    "chunk_text_fallback",
    "cosine_similarity",
    "euclidean_distance",
    "dot_product",
]
