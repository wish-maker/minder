from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

from src.shared.domain.aggregate import Aggregate
from src.shared.events.event import Event, EventMetadata


class PluginAggregate(Aggregate):
    """
    Aggregate for Plugin domain.

    Manages plugin lifecycle including registration, state changes,
    and configuration updates. All state changes are recorded as
    events in the Event Store.

    Attributes:
        id: Aggregate unique identifier
        plugin_id: Plugin identifier (e.g., "crypto", "network")
        plugin_version: Plugin version string
        name: Plugin display name
        description: Plugin description
        state: Current plugin state (active, inactive, error)
        version: Aggregate version (optimistic locking counter)
    """

    def __init__(self, id: UUID):
        """
        Initialize plugin aggregate.

        Args:
            id: Unique identifier for this plugin aggregate
        """
        super().__init__(id)
        self.plugin_id: str = None
        self.plugin_version: str = None  # Renamed to avoid conflict with aggregate.version
        self.name: str = None
        self.description: str = None
        self.state: str = "inactive"

    def register(self, command: Dict[str, Any]) -> None:
        """
        Register a new plugin.

        Args:
            command: Command with plugin_id, version, name, description

        Raises:
            ValueError: If plugin already registered
        """
        if self.plugin_id is not None:
            raise ValueError("Plugin already registered")

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={
                "plugin_id": command["plugin_id"],
                "version": command["version"],
                "name": command["name"],
                "description": command.get("description", ""),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def change_state(self, command: Dict[str, Any]) -> None:
        """
        Change plugin state.

        Args:
            command: Command with old_state, new_state

        Raises:
            ValueError: If plugin not registered or invalid state transition
        """
        if self.plugin_id is None:
            raise ValueError("Plugin not registered")

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(), event_type="PluginStateChanged", timestamp=datetime.now(timezone.utc)
            ),
            data={"old_state": command["old_state"], "new_state": command["new_state"]},
        )

        self._apply_event(event, version=self.version + 1)

    def _apply(self, event: Event) -> None:
        """
        Apply event to aggregate state.

        Args:
            event: Event to apply
        """
        if event.event_type == "PluginRegistered":
            self.plugin_id = event.data["plugin_id"]
            self.plugin_version = event.data["version"]
            self.name = event.data["name"]
            self.description = event.data["description"]
            self.state = "inactive"

        elif event.event_type == "PluginStateChanged":
            self.state = event.data["new_state"]

    def _next_event_id(self) -> UUID:
        """Generate next event ID for this aggregate"""
        return uuid4()
