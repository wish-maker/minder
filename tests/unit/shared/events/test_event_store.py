from uuid import uuid4

import pytest

from src.shared.events.event import DomainEvent
from src.shared.events.event_store import EventStoreRepository


class PluginRegistered(DomainEvent):
    """Example concrete event for testing"""

    def __init__(self, plugin_id: str, version: str):
        super().__init__()
        self.plugin_id = plugin_id
        self.version = version


class TestEventStore:
    """Test EventStore repository operations"""

    @pytest.fixture
    def event_store(self):
        """Create event store instance"""
        return EventStoreRepository("postgresql://minder:test@localhost/minder")

    @pytest.fixture
    def sample_event(self):
        """Create sample event"""
        return PluginRegistered(plugin_id="crypto", version="1.0.0")

    def test_append_event(self, event_store, sample_event):
        """Should append event to event store"""
        event_store.connect()
        aggregate_id = uuid4()
        event_store.append(aggregate_id=aggregate_id, expected_version=0, events=[sample_event])

        # Verify event was stored
        events = event_store.get_stream(aggregate_id=aggregate_id)
        assert len(events) == 1

    def test_get_events_for_aggregate(self, event_store):
        """Should retrieve all events for an aggregate"""
        event_store.connect()
        aggregate_id = uuid4()

        # Append multiple events
        events = [PluginRegistered(plugin_id=f"plugin_{i}", version="1.0.0") for i in range(3)]
        for i, event in enumerate(events):
            event_store.append(aggregate_id=aggregate_id, expected_version=i, events=[event])

        # Retrieve events
        stream = event_store.get_stream(aggregate_id=aggregate_id)
        assert len(stream) == 3

    def test_deserialize_not_implemented(self, event_store, sample_event):
        """Should raise NotImplementedError for get_stream (Task 4)"""
        event_store.connect()
        aggregate_id = uuid4()
        event_store.append(aggregate_id=aggregate_id, expected_version=0, events=[sample_event])

        # get_stream calls _deserialize_event which is not implemented
        with pytest.raises(NotImplementedError, match="Event Registry"):
            event_store.get_stream(aggregate_id=aggregate_id)
