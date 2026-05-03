"""
AI Services Aggregate

Business logic for AI operations with hybrid endpoint support (Pillar 2).
Manages RAG queries, embedding generation, and model inference.
"""

from typing import Any, Dict, List
from uuid import UUID

from src.ai_services.config.endpoints import AIEndpointResolver
from src.ai_services.domain.events.ai_events import (
    AIEndpointFallback,
    EmbeddingBatchGenerated,
    EmbeddingGenerated,
    ModelInferenceExecuted,
    RAGQueryProcessed,
)
from src.shared.domain.aggregate import Aggregate
from src.shared.events.event import Event, EventMetadata


class AIAggregate(Aggregate):
    """
    AI Services business logic with hybrid endpoint support (Pillar 2)

    Manages AI operations including:
    - RAG query processing
    - Embedding generation (single and batch)
    - Model inference
    - Endpoint fallback tracking
    """

    def __init__(self, aggregate_id: UUID, endpoint_resolver: AIEndpointResolver):
        """
        Initialize AI aggregate

        Args:
            aggregate_id: Unique identifier for this aggregate
            endpoint_resolver: Endpoint resolver for hybrid strategy
        """
        super().__init__(aggregate_id)
        self.endpoint_resolver = endpoint_resolver
        self.query_count = 0
        self.embedding_count = 0
        self.inference_count = 0
        self.fallback_count = 0

    def process_rag_query(
        self, query_id: UUID, query_text: str, retrieved_docs: List[UUID], model_response: str, latency_ms: int
    ) -> None:
        """
        Record RAG query processing

        Args:
            query_id: Unique query identifier
            query_text: The query text
            retrieved_docs: List of retrieved document IDs
            model_response: Model's response
            latency_ms: Query processing latency
        """
        endpoint = self.endpoint_resolver.get_endpoint()

        event = RAGQueryProcessed(
            query_id=query_id,
            query_text=query_text,
            retrieved_documents=retrieved_docs,
            model_response=model_response,
            latency_ms=latency_ms,
            endpoint_used=endpoint,
            model_used=self.endpoint_resolver.config.default_model,
        )

        self._apply_event(self._wrap_event(event), self.version + 1)

    def generate_embedding(self, document_id: UUID, embedding_vector: List[float], dimension: int) -> None:
        """
        Record embedding generation

        Args:
            document_id: Document ID
            embedding_vector: Generated embedding vector
            dimension: Embedding dimension
        """
        endpoint = self.endpoint_resolver.get_endpoint()

        event = EmbeddingGenerated(
            document_id=document_id,
            embedding_vector=embedding_vector,
            model_used=self.endpoint_resolver.config.embedding_model,
            endpoint_used=endpoint,
            dimension=dimension,
        )

        self._apply_event(self._wrap_event(event), self.version + 1)

    def generate_embedding_batch(
        self,
        batch_id: UUID,
        document_ids: List[UUID],
        embedding_vectors: List[List[float]],
        dimension: int,
        total_latency_ms: int,
    ) -> None:
        """
        Record batch embedding generation

        More efficient than individual embedding events for bulk operations.

        Args:
            batch_id: Batch operation ID
            document_ids: List of document IDs
            embedding_vectors: List of embedding vectors
            dimension: Embedding dimension
            total_latency_ms: Total batch processing latency
        """
        endpoint = self.endpoint_resolver.get_endpoint()

        event = EmbeddingBatchGenerated(
            batch_id=batch_id,
            document_ids=document_ids,
            embedding_vectors=embedding_vectors,
            model_used=self.endpoint_resolver.config.embedding_model,
            endpoint_used=endpoint,
            dimension=dimension,
            total_latency_ms=total_latency_ms,
        )

        self._apply_event(self._wrap_event(event), self.version + 1)

    def execute_inference(
        self,
        inference_id: UUID,
        model_id: UUID,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        inference_time_ms: int,
    ) -> None:
        """
        Record model inference

        Args:
            inference_id: Unique inference identifier
            model_id: Model ID used for inference
            input_data: Input data
            output_data: Output data
            inference_time_ms: Inference latency
        """
        endpoint = self.endpoint_resolver.get_endpoint()

        event = ModelInferenceExecuted(
            inference_id=inference_id,
            model_id=model_id,
            input_data=input_data,
            output_data=output_data,
            inference_time_ms=inference_time_ms,
            endpoint_used=endpoint,
            model_used=self.endpoint_resolver.config.default_model,
        )

        self._apply_event(self._wrap_event(event), self.version + 1)

    def record_endpoint_fallback(self, primary_endpoint: str, fallback_endpoint: str, reason: str) -> None:
        """
        Record endpoint fallback for monitoring

        Args:
            primary_endpoint: Primary endpoint that failed
            fallback_endpoint: Fallback endpoint used
            reason: Reason for fallback
        """
        event = AIEndpointFallback(
            primary_endpoint=primary_endpoint,
            fallback_endpoint=fallback_endpoint,
            reason=reason,
            strategy=self.endpoint_resolver.config.endpoint_strategy.value,
        )

        self._apply_event(self._wrap_event(event), self.version + 1)

    def _wrap_event(self, domain_event) -> Event:
        """
        Wrap domain event with metadata

        Args:
            domain_event: Domain event to wrap

        Returns:
            Wrapped event with metadata
        """
        metadata = EventMetadata(event_type=domain_event.__class__.__name__, causation_id=self.id)

        return Event(metadata=metadata, data={"aggregate_id": str(self.id), **domain_event.__dict__})

    def _apply(self, event: Event) -> None:
        """
        Apply event to aggregate state

        Args:
            event: Event to apply
        """
        # Update aggregate state based on event type
        event_type = event.metadata.event_type

        if event_type == "RAGQueryProcessed":
            self.query_count += 1
        elif event_type == "EmbeddingGenerated":
            self.embedding_count += 1
        elif event_type == "EmbeddingBatchGenerated":
            # Add number of embeddings in batch
            self.embedding_count += len(event.data.get("document_ids", []))
        elif event_type == "ModelInferenceExecuted":
            self.inference_count += 1
        elif event_type == "AIEndpointFallback":
            self.fallback_count += 1

    def get_statistics(self) -> Dict[str, int]:
        """
        Get aggregate statistics

        Returns:
            Dictionary with operation counts
        """
        return {
            "query_count": self.query_count,
            "embedding_count": self.embedding_count,
            "inference_count": self.inference_count,
            "fallback_count": self.fallback_count,
            "version": self.version,
        }
