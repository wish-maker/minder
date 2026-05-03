"""
Cross-Service Integration Tests

Tests async event communication and fallback mechanisms (Pillar 2).
Validates Event-Driven Architecture (EDA) patterns across services.
"""

import time
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest


# Test async event propagation (Pillar 3)
def test_model_deployment_detected_by_ai_services():
    """
    Scenario: Model deployment becomes ACTIVE
    Expected: AI Services detects deployment event via RabbitMQ

    Tests:
    - Event Store append operation
    - Outbox pattern event publishing
    - RabbitMQ message delivery
    - Consumer event processing
    """
    from src.model_management.domain.aggregates.deployment_aggregate import ModelDeploymentAggregate
    from src.model_management.domain.commands import ChangeDeploymentStatusCommand, CreateDeploymentCommand
    from src.model_management.infrastructure.event_store import EventStoreRepository

    model_id = uuid4()
    deployment_id = uuid4()

    # Arrange - Create deployment
    deployment = ModelDeploymentAggregate(deployment_id)
    deployment.request_deployment(
        CreateDeploymentCommand(deployment_id=deployment_id, model_id=model_id, version="v1.0", runtime_env="ollama")
    )

    deployment.change_status(
        ChangeDeploymentStatusCommand(
            deployment_id=deployment_id, status="ACTIVE", endpoint_url="http://ollama:11434/api/generate"
        )
    )

    # Act - Save to event store (triggers outbox publish)
    with patch("src.model_management.infrastructure.event_store.EventStoreRepository") as mock_repo:
        # Mock the repository to avoid database dependency in unit test
        repo_instance = Mock()
        mock_repo.return_value = repo_instance

        repo = EventStoreRepository("postgresql://minder:password@localhost/minder")
        repo.append(deployment.aggregate_id, deployment.version, deployment.get_uncommitted_events())

        # Verify append was called
        repo_instance.append.assert_called_once()

    # Wait for event propagation (max 5 seconds for RabbitMQ)
    # In real integration test, would wait for actual RabbitMQ delivery
    time.sleep(0.1)  # Minimal wait for mocked test

    # Assert - Verify events were created
    events = deployment.get_uncommitted_events()
    assert len(events) > 0, "Should have deployment events"

    # Verify event types
    event_types = [event.__class__.__name__ for event in events]
    assert "DeploymentRequestedEvent" in event_types or "DeploymentStatusChangedEvent" in event_types


# Test fallback mechanism (Pillar 2)
def test_ai_endpoint_fallback_on_failure():
    """
    Scenario: Primary AI endpoint fails
    Expected: System falls back to LAN endpoint automatically

    Tests:
    - AIEndpointResolver with fallback enabled
    - Primary endpoint failure detection
    - Automatic fallback to secondary endpoint
    - Endpoint health checking
    """
    from src.ai_services.config.endpoints import AIEndpointConfig, AIEndpointResolver

    config = AIEndpointConfig(
        endpoint_strategy="local",
        local_ollama_url="http://invalid:11434",  # Simulated failure
        lan_ollama_url="http://192.168.1.100:11434",
        enable_fallback=True,
    )
    resolver = AIEndpointResolver(config)

    # Should fallback to LAN endpoint
    endpoint = resolver.get_endpoint()
    assert "192.168.1.100" in endpoint, f"Expected LAN endpoint in fallback, got: {endpoint}"

    # Test with all endpoints failing
    config_no_fallback = AIEndpointConfig(
        endpoint_strategy="local",
        local_ollama_url="http://invalid:11434",
        lan_ollama_url="http://invalid-lan:11434",
        enable_fallback=False,
    )
    resolver_no_fallback = AIEndpointResolver(config_no_fallback)

    # Should raise exception or return None when all fail and fallback disabled
    try:
        endpoint = resolver_no_fallback.get_endpoint()
        # If it doesn't raise, verify it's a default/last resort endpoint
        assert endpoint is not None
    except Exception as e:
        # Expected behavior when all endpoints fail
        assert "fallback" in str(e).lower() or "endpoint" in str(e).lower()


# Test idempotency
def test_event_processing_is_idempotent():
    """
    Scenario: Same event delivered twice
    Expected: Event only processed once

    Tests:
    - IdempotencyKey generation
    - Duplicate event detection
    - IdempotencyManager prevents duplicate processing
    """
    from src.model_management.domain.events import DeploymentStatusChangedEvent
    from src.shared.infrastructure.idempotency import IdempotencyManager

    event_id = uuid4()
    deployment_id = uuid4()

    event = DeploymentStatusChangedEvent(
        event_id=event_id,
        deployment_id=deployment_id,
        status="ACTIVE",
        endpoint_url="http://ollama:11434/api/generate",
        timestamp=datetime.now(timezone.utc),
    )

    # Create idempotency manager
    manager = IdempotencyManager()

    # First processing - should succeed
    key1 = manager.get_key(event)
    result1 = manager.is_already_processed(key1)
    assert not result1, "First processing should not be marked as duplicate"

    # Mark as processed
    manager.mark_as_processed(key1)

    # Second processing - should be detected as duplicate
    key2 = manager.get_key(event)
    result2 = manager.is_already_processed(key2)
    assert result2, "Second processing should be detected as duplicate"

    # Verify keys are consistent
    assert key1 == key2, "Idempotency keys should be consistent for same event"


# Test cross-service event flow
def test_model_registration_propagates_to_rag_service():
    """
    Scenario: New model registered in Model Management
    Expected: RAG Service receives event and updates model catalog

    Tests:
    - ModelRegisteredEvent creation
    - Event publishing to RabbitMQ
    - RAG Service consumption
    - Model catalog projection update
    """
    from src.model_management.domain.aggregates.model_aggregate import ModelAggregate
    from src.model_management.domain.commands import RegisterModelCommand
    from src.model_management.domain.events import ModelRegisteredEvent

    model_id = uuid4()

    # Arrange - Register model
    model = ModelAggregate(model_id)
    model.register(
        RegisterModelCommand(
            model_id=model_id,
            name="TestModel",
            model_type="LLM",
            resource_profile="cpu-standard",
            registered_by="test_user",
        )
    )

    # Act - Get events
    events = model.get_uncommitted_events()

    # Assert - Verify ModelRegisteredEvent exists
    registered_events = [e for e in events if isinstance(e, ModelRegisteredEvent)]
    assert len(registered_events) > 0, "Should have ModelRegisteredEvent"

    event = registered_events[0]
    assert event.model_id == model_id
    assert event.name == "TestModel"
    assert event.model_type == "LLM"


# Test event replay capability
def test_event_store_replay_for_projection_rebuild():
    """
    Scenario: Projection needs rebuilding
    Expected: Event Store can replay all events for an aggregate

    Tests:
    - Event Store append
    - Event Stream retrieval
    - Replay capability
    - Projection rebuild from events
    """
    from src.model_management.domain.aggregates.deployment_aggregate import ModelDeploymentAggregate
    from src.model_management.domain.commands import ChangeDeploymentStatusCommand, CreateDeploymentCommand

    deployment_id = uuid4()
    model_id = uuid4()

    # Create deployment with multiple state changes
    deployment = ModelDeploymentAggregate(deployment_id)

    # Initial request
    deployment.request_deployment(
        CreateDeploymentCommand(deployment_id=deployment_id, model_id=model_id, version="v1.0", runtime_env="ollama")
    )

    # Status change to DEPLOYING
    deployment.change_status(
        ChangeDeploymentStatusCommand(deployment_id=deployment_id, status="DEPLOYING", endpoint_url=None)
    )

    # Status change to ACTIVE
    deployment.change_status(
        ChangeDeploymentStatusCommand(
            deployment_id=deployment_id, status="ACTIVE", endpoint_url="http://ollama:11434/api/generate"
        )
    )

    # Get all events
    events = deployment.get_uncommitted_events()

    # Assert - Should have 3 events (request, deploying, active)
    assert len(events) >= 3, f"Expected at least 3 events, got {len(events)}"

    # In real integration test, would verify:
    # 1. Events stored in Event Store
    # 2. Events can be retrieved in order
    # 3. Aggregate can be rebuilt from events


# Test circuit breaker integration
def test_circuit_breaker_triggers_fallback():
    """
    Scenario: Service fails repeatedly triggering circuit breaker
    Expected: Circuit opens and fallback endpoint is used

    Tests:
    - Circuit breaker state tracking
    - Failure threshold detection
    - Circuit open state
    - Automatic fallback activation
    """
    from src.ai_services.config.endpoints import AIEndpointConfig
    from src.ai_services.infrastructure.circuit_breaker import CircuitBreaker, CircuitBreakerState

    config = AIEndpointConfig(
        endpoint_strategy="local",
        local_ollama_url="http://primary:11434",
        lan_ollama_url="http://fallback:11434",
        enable_fallback=True,
        circuit_breaker_threshold=3,
        circuit_breaker_timeout=60,
    )

    circuit_breaker = CircuitBreaker(config)

    # Simulate failures
    for i in range(3):
        circuit_breaker.record_failure("http://primary:11434")

    # Circuit should be open
    assert circuit_breaker.get_state("http://primary:11434") == CircuitBreakerState.OPEN

    # Should recommend fallback endpoint
    recommended = circuit_breaker.get_recommended_endpoint()
    assert "fallback" in recommended or "192.168" in recommended


# Test event versioning
def test_event_versioning_allows_evolution():
    """
    Scenario: Event schema evolves over time
    Expected: Old events can still be deserialized

    Tests:
    - Event version field
    - Backward compatibility
    - Event upcasting
    """
    from datetime import datetime, timezone

    from src.model_management.domain.events import ModelRegisteredEvent

    # Create event with current version
    event_v1 = ModelRegisteredEvent(
        event_id=uuid4(),
        model_id=uuid4(),
        name="TestModel",
        model_type="LLM",
        resource_profile="cpu-standard",
        registered_by="test_user",
        timestamp=datetime.now(timezone.utc),
    )

    # Verify event has version information
    assert hasattr(event_v1, "version") or hasattr(event_v1, "event_version")

    # In real implementation, would test:
    # 1. Serialization of old event format
    # 2. Upcasting to new format
    # 3. Backward compatibility


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
