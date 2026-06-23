"""
Domain Layer Package

This package contains all business logic and domain models
for the RAG pipeline service. It has NO dependencies on:
- External services (Ollama, Qdrant, Redis)
- Infrastructure details
- API concerns

The domain layer is pure Python logic that can be tested independently.
"""

from .compressors import ContextualCompressor
from .expansion import HyDEQueryExpander
from .pipelines import SelfRAGPipeline
from .rerankers import CrossEncoderReranker
from .retrievers import HybridSearchRetriever, ParentChildRetriever

__all__ = [
    "HybridSearchRetriever",
    "ParentChildRetriever",
    "CrossEncoderReranker",
    "ContextualCompressor",
    "SelfRAGPipeline",
    "HyDEQueryExpander",
]
