from datetime import datetime, timezone
from uuid import uuid4

from src.shared.events.event import Event, EventMetadata
from src.shared.projections.projection import Projection


class TestProjection:
    """Test base Projection class"""

    def test_projection_creation(self):
        """Should create projection with name"""
        projection = TestPluginProjection()

        assert projection.name == "TestPluginProjection"
        assert projection.version == 0

    def test_handle_event(self):
        """Should handle event and update state"""
        projection = TestPluginProjection()

        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto", "version": "1.0.0"},
        )

        projection.handle(event)

        assert projection.version == 1
        assert projection.plugin_id == "crypto"

    def test_handle_unknown_event(self):
        """Should ignore unknown event types"""
        projection = TestPluginProjection()

        event = Event(
            metadata=EventMetadata(event_id=uuid4(), event_type="UnknownEvent", timestamp=datetime.now(timezone.utc)),
            data={},
        )

        # Should not raise error
        projection.handle(event)

        assert projection.version == 0  # No change


class TestPluginProjection(Projection):
    """Test projection for Plugin domain"""

    def __init__(self):
        super().__init__()
        self.plugin_id = None
        self.version_str = None

    def _apply(self, event: Event) -> None:
        """Apply plugin events"""
        if event.event_type == "PluginRegistered":
            self.plugin_id = event.data["plugin_id"]
            self.version_str = event.data["version"]
        else:
            # Raise exception for unknown event types
            raise ValueError(f"Unknown event type: {event.event_type}")
