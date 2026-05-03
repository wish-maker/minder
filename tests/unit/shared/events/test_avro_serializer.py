from datetime import datetime, timezone
from uuid import uuid4

from src.shared.events.avro_serializer import AvroSerializer
from src.shared.events.event import Event, EventMetadata


class TestAvroSerializer:
    """Test Avro serialization and deserialization"""

    def test_serialize_event_to_avro(self):
        """Should serialize event to Avro binary format"""
        metadata = EventMetadata(event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc))

        event = Event(metadata=metadata, data={"plugin_id": "crypto", "version": "1.0.0"})

        serializer = AvroSerializer()
        avro_bytes = serializer.serialize(event)

        assert isinstance(avro_bytes, bytes)
        assert len(avro_bytes) > 0

    def test_deserialize_avro_to_event(self):
        """Should deserialize Avro bytes back to event"""
        metadata = EventMetadata(event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc))

        original_event = Event(metadata=metadata, data={"plugin_id": "crypto", "version": "1.0.0"})

        serializer = AvroSerializer()
        avro_bytes = serializer.serialize(original_event)
        restored_event = serializer.deserialize(avro_bytes)

        assert restored_event.metadata.event_id == original_event.metadata.event_id
        assert restored_event.metadata.event_type == "PluginRegistered"
        assert restored_event.data["plugin_id"] == "crypto"
        assert restored_event.data["version"] == "1.0.0"

    def test_round_trip_serialization(self):
        """Should preserve data integrity through serialize/deserialize"""
        event_id = uuid4()
        correlation_id = uuid4()
        timestamp = datetime.now(timezone.utc)

        metadata = EventMetadata(
            event_id=event_id,
            event_type="PluginStateChanged",
            timestamp=timestamp,
            correlation_id=correlation_id,
            user_id="user123",
            trace_id="trace-abc",
        )

        original_event = Event(
            metadata=metadata, data={"plugin_id": "network", "old_state": "inactive", "new_state": "active"}
        )

        serializer = AvroSerializer()
        avro_bytes = serializer.serialize(original_event)
        restored_event = serializer.deserialize(avro_bytes)

        # Verify all fields preserved
        assert restored_event.metadata.event_id == event_id
        assert restored_event.metadata.event_type == "PluginStateChanged"
        assert restored_event.metadata.correlation_id == correlation_id
        assert restored_event.metadata.user_id == "user123"
        assert restored_event.metadata.trace_id == "trace-abc"
        assert restored_event.data["plugin_id"] == "network"
        assert restored_event.data["old_state"] == "inactive"
        assert restored_event.data["new_state"] == "active"

    def test_get_avro_schema(self):
        """Should generate Avro schema for Event type"""
        serializer = AvroSerializer()
        schema = serializer.get_schema()

        assert schema["type"] == "record"
        assert schema["name"] == "Event"
        assert "fields" in schema
        assert len(schema["fields"]) == 2  # metadata and data

    def test_validate_event_with_schema(self):
        """Should validate event against Avro schema"""
        metadata = EventMetadata(event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc))

        event = Event(metadata=metadata, data={"plugin_id": "crypto", "version": "1.0.0"})

        serializer = AvroSerializer()
        # Should not raise exception
        serializer.validate(event)
