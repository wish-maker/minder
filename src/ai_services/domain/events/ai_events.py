"""
AI Services Domain Events

Domain events for AI operations including RAG queries, embeddings,
and model inference. Tracks endpoint usage for Pillar 2 hybrid strategy.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import UUID, uuid4

from src.shared.events.event import DomainEvent


@dataclass
class RAGQueryProcessed(DomainEvent):
    """
    RAG query processed event

    Emitted when a RAG (Retrieval-Augmented Generation) query is processed.
    Tracks the query, retrieved documents, response, and which endpoint was used.
    """

    query_id: UUID = field(default_factory=uuid4)
    query_text: str = ""
    retrieved_documents: List[UUID] = field(default_factory=list)
    model_response: str = ""
    latency_ms: int = 0
    endpoint_used: str = ""  # Track which endpoint was used (Pillar 2)
    model_used: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EmbeddingGenerated(DomainEvent):
    """
    Embedding generated event

    Emitted when an embedding vector is generated for a document.
    Tracks the document, embedding vector, model, and endpoint used.
    """

    document_id: UUID = field(default_factory=uuid4)
    embedding_vector: List[float] = field(default_factory=list)
    model_used: str = ""
    endpoint_used: str = ""  # Track which endpoint was used (Pillar 2)
    dimension: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ModelInferenceExecuted(DomainEvent):
    """
    Model inference executed event

    Emitted when a model inference is executed.
    Tracks the inference request, response, timing, and endpoint used.
    """

    inference_id: UUID = field(default_factory=uuid4)
    model_id: UUID = field(default_factory=uuid4)
    input_data: Dict[str, Any] = field(default_factory=dict)
    output_data: Dict[str, Any] = field(default_factory=dict)
    inference_time_ms: int = 0
    endpoint_used: str = ""  # Track which endpoint was used (Pillar 2)
    model_used: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AIEndpointFallback(DomainEvent):
    """
    AI endpoint fallback event

    Emitted when the system falls back from the primary endpoint
    to an alternative endpoint. Useful for monitoring endpoint health.
    """

    primary_endpoint: str = ""
    fallback_endpoint: str = ""
    reason: str = ""  # e.g., "timeout", "connection_error", "unhealthy"
    strategy: str = ""  # The configured strategy (local, lan, cloud)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class EmbeddingBatchGenerated(DomainEvent):
    """
    Batch embedding generation event

    Emitted when multiple embeddings are generated in a batch operation.
    More efficient than individual EmbeddingGenerated events.
    """

    batch_id: UUID = field(default_factory=uuid4)
    document_ids: List[UUID] = field(default_factory=list)
    embedding_vectors: List[List[float]] = field(default_factory=list)
    model_used: str = ""
    endpoint_used: str = ""
    dimension: int = 0
    total_latency_ms: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
