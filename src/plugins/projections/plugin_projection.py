from typing import Optional
from uuid import UUID

from src.shared.events.event import Event
from src.shared.projections.projection import Projection


class PluginProjection(Projection):
    """
    Read model projection for Plugin domain.

    Maintains denormalized plugin state optimized for querying.
    Subscribes to plugin-related events and updates state accordingly.

    Attributes:
        id: Unique identifier for this projection
        plugin_id: Plugin identifier (e.g., "crypto", "network")
        version_str: Plugin version string
        name: Plugin display name
        description: Plugin description
        state: Current plugin state (active, inactive, error)
    """

    def __init__(self, id: UUID):
        """
        Initialize plugin projection.

        Args:
            id: Unique identifier for this projection
        """
        super().__init__(id)
        self.plugin_id: Optional[str] = None
        self.version_str: Optional[str] = None
        # Note: 'name' is inherited from Projection base class
        # It will be overwritten with plugin display name when PluginRegistered event is handled
        self.description: Optional[str] = None
        self.state: str = "inactive"

    def _apply(self, event: Event) -> None:
        """
        Apply plugin-related events to projection state.

        Handles:
        - PluginRegistered: Initialize plugin state
        - PluginStateChanged: Update plugin state

        Args:
            event: Event to apply

        Note:
            Unknown event types are silently ignored as per projection spec.
        """
        if event.event_type == "PluginRegistered":
            self.plugin_id = event.data["plugin_id"]
            self.version_str = event.data["version"]
            self.name = event.data["name"]
            self.description = event.data.get("description", "")
            self.state = "inactive"

        elif event.event_type == "PluginStateChanged":
            self.state = event.data["new_state"]

        # Unknown event types are ignored (no else clause)
