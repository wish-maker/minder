"""
Compressors Package

This package contains context compression strategies for reducing
retrieved context size while preserving relevance.
"""

from .contextual import ContextualCompressor

__all__ = [
    "ContextualCompressor",
]
