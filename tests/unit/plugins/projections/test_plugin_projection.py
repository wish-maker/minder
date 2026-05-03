from datetime import datetime, timezone
from uuid import uuid4

from src.plugins.projections.plugin_projection import PluginProjection
from src.shared.events.event import Event, EventMetadata


class TestPluginProjection:
    """Test PluginProjection read model"""

    def test_projection_creation(self):
        """Should create projection with correct name"""
        projection = PluginProjection(id=uuid4())

        assert projection.name == "PluginProjection"
        assert projection.version == 0
        assert projection.id is not None

    def test_handle_plugin_registered(self):
        """Should handle PluginRegistered event"""
        projection = PluginProjection(id=uuid4())

        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={
                "plugin_id": "crypto",
                "version": "1.0.0",
                "name": "Crypto Plugin",
                "description": "Cryptocurrency plugin",
            },
        )

        projection.handle(event)

        assert projection.version == 1
        assert projection.plugin_id == "crypto"
        assert projection.version_str == "1.0.0"
        assert projection.name == "Crypto Plugin"
        assert projection.description == "Cryptocurrency plugin"
        assert projection.state == "inactive"

    def test_handle_plugin_state_changed(self):
        """Should handle PluginStateChanged event"""
        projection = PluginProjection(id=uuid4())

        # First register plugin
        registered_event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "network", "version": "1.0.0", "name": "Network Plugin"},
        )
        projection.handle(registered_event)

        # Then change state
        state_event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginStateChanged", timestamp=datetime.now(timezone.utc)
            ),
            data={"old_state": "inactive", "new_state": "active"},
        )

        projection.handle(state_event)

        assert projection.version == 2
        assert projection.state == "active"

    def test_handle_unknown_event(self):
        """Should ignore unknown event types (no state change, but version increments)"""
        projection = PluginProjection(id=uuid4())

        event = Event(
            metadata=EventMetadata(event_id=uuid4(), event_type="UnknownEvent", timestamp=datetime.now(timezone.utc)),
            data={},
        )

        # Should not raise error
        projection.handle(event)

        # Version increments because event was processed (even if not handled)
        assert projection.version == 1
        # Projection state remains unchanged
        assert projection.plugin_id is None
        assert projection.version_str is None
        assert projection.description is None
        assert projection.state == "inactive"
