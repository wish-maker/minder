# src/plugin_state_manager/domain/aggregates/state_aggregate.py

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from uuid import UUID

from src.shared.domain.aggregate import Aggregate
from src.shared.events.event import Event, EventMetadata


class PluginState(Enum):
    """Plugin lifecycle states"""

    INSTALLED = "installed"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"


class PluginStateAggregate(Aggregate):
    """
    Aggregate for Plugin State Manager domain.

    Manages plugin state lifecycle including state transitions and tool
    execution tracking. All state changes are recorded as events in the
    Event Store for audit and replay capabilities.

    Attributes:
        id: Aggregate unique identifier
        plugin_id: Plugin identifier
        state: Current plugin state
        last_activity: Last activity timestamp
        tool_execution_count: Number of tools executed
    """

    def __init__(self, id: UUID):
        """
        Initialize plugin state aggregate.

        Args:
            id: Unique identifier for this aggregate
        """
        super().__init__(id)
        self.plugin_id: Optional[UUID] = None
        self.state: PluginState = PluginState.INSTALLED
        self.last_activity: Optional[datetime] = None
        self.tool_execution_count: int = 0

    def update_state(self, new_state: str, reason: str = "") -> None:
        """
        Update plugin state.

        Args:
            new_state: New state value (installed, running, stopped, error)
            reason: Reason for state change

        Raises:
            ValueError: If new_state is not a valid PluginState
        """
        # Validate new state
        try:
            PluginState(new_state)
        except ValueError:
            raise ValueError(f"Invalid state: {new_state}. Must be one of: {[s.value for s in PluginState]}")

        old_state = self.state.value

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="PluginStateUpdated",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "plugin_id": str(self.id),
                "old_state": old_state,
                "new_state": new_state,
                "changed_at": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            },
        )

        self._apply_event(event, version=self.version + 1)

    def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> None:
        """
        Execute plugin tool.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool execution parameters

        Raises:
            ValueError: If plugin is not in RUNNING state
        """
        if self.state != PluginState.RUNNING:
            raise ValueError(f"Cannot execute tool: plugin is not running (current state: {self.state.value})")

        result = {"success": True, "output": "Tool executed"}

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="PluginToolExecuted",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "plugin_id": str(self.id),
                "tool_name": tool_name,
                "tool_parameters": parameters,
                "execution_result": result,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def _apply(self, event: Event) -> None:
        """
        Apply event to aggregate state.

        Args:
            event: Event to apply
        """
        if event.event_type == "PluginStateUpdated":
            self._apply_plugin_state_updated(event)
        elif event.event_type == "PluginToolExecuted":
            self._apply_plugin_tool_executed(event)

    def _apply_plugin_state_updated(self, event: Event) -> None:
        """Apply PluginStateUpdated event to aggregate state"""
        self.plugin_id = UUID(event.data["plugin_id"])
        self.state = PluginState(event.data["new_state"])
        self.last_activity = datetime.fromisoformat(event.data["changed_at"])

    def _apply_plugin_tool_executed(self, event: Event) -> None:
        """Apply PluginToolExecuted event to aggregate state"""
        self.plugin_id = UUID(event.data["plugin_id"])
        self.tool_execution_count += 1
        self.last_activity = datetime.fromisoformat(event.data["executed_at"])

    def _next_event_id(self) -> UUID:
        """Generate next event ID for this aggregate"""
        from uuid import uuid4

        return uuid4()
