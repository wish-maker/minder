"""
Tests for AI Aggregate

Tests AI services business logic including RAG queries,
embeddings, and inference with endpoint tracking.
"""

from uuid import UUID, uuid4

import pytest

from src.ai_services.config.endpoints import AIEndpointConfig, AIEndpointResolver
from src.ai_services.domain.aggregates.ai_aggregate import AIAggregate


class TestAIAggregate:
    """Test AI aggregate operations"""

    @pytest.fixture
    def config(self):
        """Create test configuration"""
        return AIEndpointConfig(endpoint_strategy="local", enable_fallback=False)

    @pytest.fixture
    def resolver(self, config):
        """Create test endpoint resolver"""
        return AIEndpointResolver(config)

    @pytest.fixture
    def aggregate(self, resolver):
        """Create test AI aggregate"""
        aggregate_id = uuid4()
        return AIAggregate(aggregate_id, resolver)

    def test_aggregate_initialization(self, aggregate):
        """Test aggregate initialization"""
        assert aggregate.id is not None
        assert isinstance(aggregate.id, UUID)
        assert aggregate.query_count == 0
        assert aggregate.embedding_count == 0
        assert aggregate.inference_count == 0
        assert aggregate.fallback_count == 0
        assert aggregate.version == 0

    def test_process_rag_query(self, aggregate):
        """Test RAG query processing"""
        query_id = uuid4()
        query_text = "What is the capital of France?"
        retrieved_docs = [uuid4(), uuid4(), uuid4()]
        model_response = "The capital of France is Paris."
        latency_ms = 250

        aggregate.process_rag_query(
            query_id=query_id,
            query_text=query_text,
            retrieved_docs=retrieved_docs,
            model_response=model_response,
            latency_ms=latency_ms,
        )

        # Check aggregate state
        assert aggregate.query_count == 1

        # Check event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1

        event = events[0]
        assert event.metadata.event_type == "RAGQueryProcessed"
        assert event.data["query_id"] == query_id or event.data["query_id"] == str(query_id)
        assert event.data["query_text"] == query_text
        assert event.data["model_response"] == model_response
        assert event.data["latency_ms"] == latency_ms
        assert "endpoint_used" in event.data

    def test_generate_embedding(self, aggregate):
        """Test embedding generation"""
        document_id = uuid4()
        embedding_vector = [0.1, 0.2, 0.3, 0.4]
        dimension = 4

        aggregate.generate_embedding(document_id=document_id, embedding_vector=embedding_vector, dimension=dimension)

        # Check aggregate state
        assert aggregate.embedding_count == 1

        # Check event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1

        event = events[0]
        assert event.metadata.event_type == "EmbeddingGenerated"
        assert event.data["document_id"] == document_id or event.data["document_id"] == str(document_id)
        assert event.data["embedding_vector"] == embedding_vector
        assert event.data["dimension"] == dimension
        assert "endpoint_used" in event.data

    def test_generate_embedding_batch(self, aggregate):
        """Test batch embedding generation"""
        batch_id = uuid4()
        document_ids = [uuid4(), uuid4(), uuid4()]
        embedding_vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]
        dimension = 3
        total_latency_ms = 500

        aggregate.generate_embedding_batch(
            batch_id=batch_id,
            document_ids=document_ids,
            embedding_vectors=embedding_vectors,
            dimension=dimension,
            total_latency_ms=total_latency_ms,
        )

        # Check aggregate state (should increment by batch size)
        assert aggregate.embedding_count == 3

        # Check event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1

        event = events[0]
        assert event.metadata.event_type == "EmbeddingBatchGenerated"
        assert event.data["batch_id"] == batch_id or event.data["batch_id"] == str(batch_id)
        assert len(event.data["document_ids"]) == 3
        assert event.data["total_latency_ms"] == total_latency_ms

    def test_execute_inference(self, aggregate):
        """Test model inference execution"""
        inference_id = uuid4()
        model_id = uuid4()
        input_data = {"prompt": "Hello, world!"}
        output_data = {"response": "Hi there!"}
        inference_time_ms = 150

        aggregate.execute_inference(
            inference_id=inference_id,
            model_id=model_id,
            input_data=input_data,
            output_data=output_data,
            inference_time_ms=inference_time_ms,
        )

        # Check aggregate state
        assert aggregate.inference_count == 1

        # Check event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1

        event = events[0]
        assert event.metadata.event_type == "ModelInferenceExecuted"
        assert event.data["inference_id"] == inference_id or event.data["inference_id"] == str(inference_id)
        assert event.data["model_id"] == model_id or event.data["model_id"] == str(model_id)
        assert event.data["input_data"] == input_data
        assert event.data["output_data"] == output_data
        assert event.data["inference_time_ms"] == inference_time_ms
        assert "endpoint_used" in event.data

    def test_record_endpoint_fallback(self, aggregate):
        """Test endpoint fallback recording"""
        primary_endpoint = "http://local:11434"
        fallback_endpoint = "http://192.168.1.100:11434"
        reason = "timeout"

        aggregate.record_endpoint_fallback(
            primary_endpoint=primary_endpoint, fallback_endpoint=fallback_endpoint, reason=reason
        )

        # Check aggregate state
        assert aggregate.fallback_count == 1

        # Check event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1

        event = events[0]
        assert event.metadata.event_type == "AIEndpointFallback"
        assert event.data["primary_endpoint"] == primary_endpoint
        assert event.data["fallback_endpoint"] == fallback_endpoint
        assert event.data["reason"] == reason
        assert "strategy" in event.data

    def test_get_statistics(self, aggregate):
        """Test getting aggregate statistics"""
        # Perform some operations
        query_id = uuid4()
        aggregate.process_rag_query(
            query_id=query_id,
            query_text="test query",
            retrieved_docs=[uuid4()],
            model_response="test response",
            latency_ms=100,
        )

        document_id = uuid4()
        aggregate.generate_embedding(document_id=document_id, embedding_vector=[0.1, 0.2], dimension=2)

        inference_id = uuid4()
        aggregate.execute_inference(
            inference_id=inference_id,
            model_id=uuid4(),
            input_data={"test": "data"},
            output_data={"result": "success"},
            inference_time_ms=50,
        )

        # Get statistics
        stats = aggregate.get_statistics()

        assert stats["query_count"] == 1
        assert stats["embedding_count"] == 1
        assert stats["inference_count"] == 1
        assert stats["fallback_count"] == 0
        assert stats["version"] == 3  # 3 events applied

    def test_mark_events_as_committed(self, aggregate):
        """Test marking events as committed"""
        # Create an event
        aggregate.process_rag_query(
            query_id=uuid4(), query_text="test", retrieved_docs=[], model_response="response", latency_ms=100
        )

        # Verify event exists
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1

        # Mark as committed
        aggregate.mark_events_as_committed()

        # Verify events cleared
        events = aggregate.get_uncommitted_events()
        assert len(events) == 0

    def test_event_applies_to_aggregate_state(self, aggregate):
        """Test that events properly update aggregate state"""
        # Process multiple RAG queries
        for i in range(5):
            aggregate.process_rag_query(
                query_id=uuid4(),
                query_text=f"Query {i}",
                retrieved_docs=[uuid4()],
                model_response=f"Response {i}",
                latency_ms=100 + i * 10,
            )

        # State should be updated
        assert aggregate.query_count == 5
        assert aggregate.version == 5

    def test_batch_embedding_state_update(self, aggregate):
        """Test that batch embeddings update state correctly"""
        # Create batch with 10 embeddings
        document_ids = [uuid4() for _ in range(10)]
        embedding_vectors = [[0.1, 0.2, 0.3] for _ in range(10)]

        aggregate.generate_embedding_batch(
            batch_id=uuid4(),
            document_ids=document_ids,
            embedding_vectors=embedding_vectors,
            dimension=3,
            total_latency_ms=1000,
        )

        # Should increment by 10, not 1
        assert aggregate.embedding_count == 10
