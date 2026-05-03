# src/plugin_state_manager/domain/events/state_events.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID, uuid4

from src.shared.events.event import DomainEvent


@dataclass
class PluginStateUpdated(DomainEvent):
    """Emitted when plugin state changes"""

    plugin_id: UUID = field(default_factory=uuid4)
    old_state: str = ""
    new_state: str = ""  # INSTALLED, RUNNING, STOPPED, ERROR
    changed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str = ""


@dataclass
class PluginToolExecuted(DomainEvent):
    """Emitted when plugin tool is executed"""

    plugin_id: UUID = field(default_factory=uuid4)
    tool_name: str = ""
    tool_parameters: Dict[str, Any] = field(default_factory=dict)
    execution_result: Dict[str, Any] = field(default_factory=dict)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
