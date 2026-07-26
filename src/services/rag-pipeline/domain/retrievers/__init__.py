"""
Retrievers Package

This package contains various retrieval strategies for fetching
relevant documents from knowledge bases.
"""

from .hybrid import HybridSearchRetriever

__all__ = [
    "HybridSearchRetriever",
]
