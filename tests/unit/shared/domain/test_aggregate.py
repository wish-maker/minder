from datetime import datetime, timezone
from uuid import UUID, uuid4

from src.shared.domain.aggregate import Aggregate
from src.shared.events.event import Event, EventMetadata


class PluginAggregate(Aggregate):
    """Test aggregate for Plugin domain"""

    def __init__(self, id: UUID):
        super().__init__(id)
        self.plugin_id = None

    def _apply(self, event: Event) -> None:
        """Apply event to aggregate state"""
        # Store event data for testing
        if event.data.get("plugin_id"):
            self.plugin_id = event.data["plugin_id"]
        if event.data.get("state"):
            self.state = event.data["state"]


class TestAggregate:
    """Test base Aggregate class"""

    def test_create_aggregate(self):
        """Should create aggregate with ID"""
        aggregate_id = uuid4()
        aggregate = PluginAggregate(aggregate_id)

        assert aggregate.id == aggregate_id
        assert aggregate.version == 0
        assert len(aggregate._uncommitted_events) == 0

    def test_apply_event(self):
        """Should apply event and update state"""
        aggregate = PluginAggregate(uuid4())

        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto", "version": "1.0.0"},
        )

        aggregate._apply_event(event, version=1)

        assert aggregate.version == 1
        assert len(aggregate._uncommitted_events) == 1

    def test_load_from_history(self):
        """Should rebuild state from event history"""
        aggregate_id = uuid4()

        # Create event history
        events = [
            Event(
                metadata=EventMetadata(
                    event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
                ),
                data={"plugin_id": "crypto"},
            ),
            Event(
                metadata=EventMetadata(
                    event_id=uuid4(), event_type="PluginStateChanged", timestamp=datetime.now(timezone.utc)
                ),
                data={"state": "active"},
            ),
        ]

        aggregate = PluginAggregate(aggregate_id)
        aggregate.load_from_history(events)

        assert aggregate.version == 2
        assert len(aggregate._uncommitted_events) == 0  # No uncommitted events

    def test_get_uncommitted_events(self):
        """Should return uncommitted events"""
        aggregate = PluginAggregate(uuid4())

        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto"},
        )

        aggregate._apply_event(event, version=1)

        uncommitted = aggregate.get_uncommitted_events()
        assert len(uncommitted) == 1
        assert uncommitted[0].event_type == "PluginRegistered"

    def test_mark_events_as_committed(self):
        """Should clear uncommitted events"""
        aggregate = PluginAggregate(uuid4())

        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto"},
        )

        aggregate._apply_event(event, version=1)
        assert len(aggregate.get_uncommitted_events()) == 1

        aggregate.mark_events_as_committed()
        assert len(aggregate.get_uncommitted_events()) == 0
