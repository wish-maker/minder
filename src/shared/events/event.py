# src/shared/events/event.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID, uuid4


@dataclass
class EventMetadata:
    """Metadata attached to all events"""

    event_id: UUID = field(default_factory=uuid4)
    event_type: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None
    is_replay: bool = False
    replay_reason: Optional[str] = None


@dataclass
class DomainEvent:
    """Base class for all domain events"""

    event_id: UUID = field(default_factory=uuid4)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.metadata:
            self.metadata = {}


@dataclass
class Event:
    """
    Generic event wrapper for event sourcing.

    Wraps domain events with metadata and serialization information.
    Used by aggregates and event store for persistence and replay.
    """

    metadata: EventMetadata
    data: Dict[str, Any]

    @property
    def event_type(self) -> str:
        """Get event type from metadata"""
        return self.metadata.event_type

    @property
    def event_id(self) -> UUID:
        """Get event ID from metadata"""
        return self.metadata.event_id

    @property
    def timestamp(self) -> datetime:
        """Get timestamp from metadata"""
        return self.metadata.timestamp
