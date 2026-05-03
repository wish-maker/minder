from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.shared.events.event import Event, EventMetadata
from src.shared.events.event_store import EventStore


class TestEventStore:
    """Test EventStore repository operations"""

    @pytest.fixture
    def event_store(self, db_session):
        """Create event store instance"""
        return EventStore(db_session)

    @pytest.fixture
    def sample_event(self):
        """Create sample event"""
        return Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto", "version": "1.0.0"},
        )

    def test_append_event(self, event_store, sample_event):
        """Should append event to event store"""
        aggregate_id = uuid4()
        event_store.append(event=sample_event, aggregate_type="Plugin", aggregate_id=aggregate_id, version=1)

        # Verify event was stored
        events = event_store.get_events(aggregate_type="Plugin", aggregate_id=aggregate_id)
        assert len(events) == 1
        assert events[0].event_type == "PluginRegistered"

    def test_get_events_for_aggregate(self, event_store):
        """Should retrieve all events for an aggregate"""
        aggregate_id = uuid4()

        # Append multiple events
        for i in range(3):
            event = Event(
                metadata=EventMetadata(event_id=uuid4(), event_type=f"Event{i}", timestamp=datetime.now(timezone.utc)),
                data={"index": i},
            )
            event_store.append(event=event, aggregate_type="Plugin", aggregate_id=aggregate_id, version=i + 1)

        # Retrieve events
        events = event_store.get_events(aggregate_type="Plugin", aggregate_id=aggregate_id)
        assert len(events) == 3
        assert events[0].event_type == "Event0"
        assert events[2].event_type == "Event2"

    def test_get_events_from_version(self, event_store):
        """Should retrieve events from specific version"""
        aggregate_id = uuid4()

        # Append 5 events
        for i in range(5):
            event = Event(
                metadata=EventMetadata(event_id=uuid4(), event_type=f"Event{i}", timestamp=datetime.now(timezone.utc)),
                data={"index": i},
            )
            event_store.append(event=event, aggregate_type="Plugin", aggregate_id=aggregate_id, version=i + 1)

        # Get events from version 3
        events = event_store.get_events(aggregate_type="Plugin", aggregate_id=aggregate_id, from_version=3)
        assert len(events) == 3  # versions 3, 4, 5
        assert events[0].event_type == "Event2"

    def test_save_snapshot(self, event_store):
        """Should save aggregate snapshot"""
        aggregate_id = uuid4()
        state = {"plugin_id": "crypto", "state": "active"}

        event_store.save_snapshot(aggregate_type="Plugin", aggregate_id=aggregate_id, version=100, state=state)

        # Retrieve snapshot
        snapshot = event_store.get_latest_snapshot(aggregate_type="Plugin", aggregate_id=aggregate_id)
        assert snapshot is not None
        assert snapshot["version"] == 100
        assert snapshot["state"]["plugin_id"] == "crypto"

    def test_get_latest_snapshot(self, event_store):
        """Should get latest snapshot for aggregate"""
        aggregate_id = uuid4()

        # Save multiple snapshots
        for version in [50, 100, 150]:
            event_store.save_snapshot(
                aggregate_type="Plugin", aggregate_id=aggregate_id, version=version, state={"version": version}
            )

        # Get latest
        snapshot = event_store.get_latest_snapshot(aggregate_type="Plugin", aggregate_id=aggregate_id)
        assert snapshot["version"] == 150
