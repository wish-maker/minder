import pytest

from src.shared.events.avro_serializer import AvroEventSerializer
from src.shared.events.event import DomainEvent


class PluginRegistered(DomainEvent):
    """Example concrete event for testing"""

    def __init__(self, plugin_id: str, version: str):
        super().__init__()
        self.plugin_id = plugin_id
        self.version = version


class TestAvroEventSerializer:
    """Test Avro serialization"""

    def test_serialize_event_to_avro(self):
        """Should serialize event to Avro binary format"""
        event = PluginRegistered(plugin_id="crypto", version="1.0.0")

        serializer = AvroEventSerializer()
        avro_bytes = serializer.serialize(event)

        assert isinstance(avro_bytes, bytes)
        assert len(avro_bytes) > 0

    def test_deserialize_not_implemented(self):
        """Should raise NotImplementedError for deserialize (Task 4)"""
        event = PluginRegistered(plugin_id="crypto", version="1.0.0")

        serializer = AvroEventSerializer()
        avro_bytes = serializer.serialize(event)

        with pytest.raises(NotImplementedError, match="Event Registry"):
            serializer.deserialize(avro_bytes, "PluginRegistered")
