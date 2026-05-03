from datetime import datetime, timezone
from uuid import uuid4

from src.plugins.domain.plugin_aggregate import PluginAggregate
from src.shared.events.event import Event, EventMetadata


class TestPluginAggregate:
    """Test PluginAggregate domain logic"""

    def test_register_plugin(self):
        """Should register new plugin"""
        aggregate_id = uuid4()
        aggregate = PluginAggregate(aggregate_id)

        command = {
            "plugin_id": "crypto",
            "version": "1.0.0",
            "name": "Crypto Plugin",
            "description": "Cryptocurrency plugin",
        }

        aggregate.register(command)

        events = aggregate.get_uncommitted_events()
        assert len(events) == 1
        assert events[0].event_type == "PluginRegistered"
        assert events[0].data["plugin_id"] == "crypto"
        assert aggregate.plugin_id == "crypto"
        assert aggregate.plugin_version == "1.0.0"

    def test_change_plugin_state(self):
        """Should change plugin state"""
        aggregate_id = uuid4()
        aggregate = PluginAggregate(aggregate_id)

        # First register the plugin
        aggregate.register({"plugin_id": "network", "version": "1.0.0", "name": "Network Plugin"})
        aggregate.mark_events_as_committed()

        # Then change state
        aggregate.change_state({"old_state": "inactive", "new_state": "active"})

        events = aggregate.get_uncommitted_events()
        assert len(events) == 1
        assert events[0].event_type == "PluginStateChanged"
        assert events[0].data["old_state"] == "inactive"
        assert events[0].data["new_state"] == "active"
        assert aggregate.state == "active"

    def test_load_from_history(self):
        """Should rebuild state from event history"""
        aggregate_id = uuid4()

        events = [
            Event(
                metadata=EventMetadata(
                    event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
                ),
                data={"plugin_id": "crypto", "version": "1.0.0", "name": "Crypto", "description": ""},
            ),
            Event(
                metadata=EventMetadata(
                    event_id=uuid4(), event_type="PluginStateChanged", timestamp=datetime.now(timezone.utc)
                ),
                data={"old_state": "inactive", "new_state": "active"},
            ),
        ]

        aggregate = PluginAggregate(aggregate_id)
        aggregate.load_from_history(events)

        assert aggregate.plugin_id == "crypto"
        assert aggregate.plugin_version == "1.0.0"
        assert aggregate.state == "active"
        assert aggregate.version == 2
