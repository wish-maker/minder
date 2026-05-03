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
