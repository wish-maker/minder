"""
Pipelines Package

This package contains RAG pipeline orchestration logic that combines
multiple retrieval and generation strategies.
"""

from .self_rag import SelfRAGPipeline

__all__ = [
    "SelfRAGPipeline",
]
