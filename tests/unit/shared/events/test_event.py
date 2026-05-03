from datetime import datetime, timezone
from uuid import uuid4

from src.shared.events.event import Event, EventMetadata


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

    def test_metadata_to_dict(self):
        """Should serialize metadata to dictionary"""
        event_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        metadata = EventMetadata(
            event_id=event_id,
            event_type="PluginRegistered",
            timestamp=timestamp,
            correlation_id=uuid4(),
            causation_id=uuid4(),
        )

        data = metadata.to_dict()
        assert data["event_id"] == str(event_id)
        assert data["event_type"] == "PluginRegistered"
        assert "timestamp" in data
        assert "correlation_id" in data
        assert "causation_id" in data

    def test_metadata_from_dict(self):
        """Should deserialize metadata from dictionary"""
        event_id = uuid4()
        correlation_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        data = {
            "event_id": str(event_id),
            "event_type": "PluginRegistered",
            "timestamp": timestamp.isoformat(),
            "correlation_id": str(correlation_id),
            "causation_id": None,
            "user_id": None,
            "trace_id": None,
        }

        metadata = EventMetadata.from_dict(data)
        assert metadata.event_id == event_id
        assert metadata.event_type == "PluginRegistered"
        assert metadata.correlation_id == correlation_id
        assert metadata.causation_id is None


class TestEvent:
    """Test base Event class"""

    def test_create_event(self):
        """Should create event with metadata and data"""
        metadata = EventMetadata(event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc))

        event = Event(metadata=metadata, data={"plugin_id": "crypto", "version": "1.0.0"})

        assert event.metadata == metadata
        assert event.data == {"plugin_id": "crypto", "version": "1.0.0"}

    def test_event_to_dict(self):
        """Should serialize event to dictionary"""
        metadata = EventMetadata(event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc))

        event = Event(metadata=metadata, data={"plugin_id": "crypto"})

        data = event.to_dict()
        assert "metadata" in data
        assert "data" in data
        assert data["data"]["plugin_id"] == "crypto"

    def test_event_from_dict(self):
        """Should deserialize event from dictionary"""
        event_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        data = {
            "metadata": {
                "event_id": str(event_id),
                "event_type": "PluginRegistered",
                "timestamp": timestamp.isoformat(),
                "correlation_id": None,
                "causation_id": None,
                "user_id": None,
                "trace_id": None,
            },
            "data": {"plugin_id": "crypto"},
        }

        event = Event.from_dict(data)
        assert event.metadata.event_id == event_id
        assert event.data["plugin_id"] == "crypto"

    def test_event_type_property(self):
        """Should expose event type from metadata"""
        metadata = EventMetadata(
            event_id=uuid4(), event_type="PluginStateChanged", timestamp=datetime.now(timezone.utc)
        )

        event = Event(metadata=metadata, data={})
        assert event.event_type == "PluginStateChanged"
