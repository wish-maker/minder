from datetime import datetime, timezone
from uuid import uuid4

from src.shared.events.event import DomainEvent, EventMetadata


class TestEventMetadata:
    """Test EventMetadata creation and validation"""

    def test_create_minimal_metadata(self):
        """Should create metadata with only required fields"""
        metadata = EventMetadata(event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc))
        assert metadata.event_id is not None
        assert metadata.event_type == "PluginRegistered"
        assert metadata.timestamp is not None
        assert metadata.correlation_id is None
        assert metadata.causation_id is None

    def test_create_full_metadata(self):
        """Should create metadata with all fields"""
        event_id = uuid4()
        correlation_id = uuid4()
        causation_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        metadata = EventMetadata(
            event_id=event_id,
            event_type="PluginRegistered",
            timestamp=timestamp,
            correlation_id=correlation_id,
            causation_id=causation_id,
            user_id="user123",
            trace_id="trace-abc",
        )
        assert metadata.event_id == event_id
        assert metadata.event_type == "PluginRegistered"
        assert metadata.timestamp == timestamp
        assert metadata.correlation_id == correlation_id
        assert metadata.causation_id == causation_id
        assert metadata.user_id == "user123"
        assert metadata.trace_id == "trace-abc"


class TestDomainEvent:
    """Test base DomainEvent class"""

    def test_create_domain_event(self):
        """Should create event with event_id and metadata"""
        event = DomainEvent()

        assert event.event_id is not None
        assert isinstance(event.metadata, dict)
        assert event.metadata == {}

    def test_domain_event_with_custom_metadata(self):
        """Should create event with custom metadata"""
        custom_metadata = {"source": "test", "version": "1.0"}
        event = DomainEvent(metadata=custom_metadata)

        assert event.metadata == custom_metadata
