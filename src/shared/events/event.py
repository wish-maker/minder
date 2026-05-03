from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass
class EventMetadata:
    """
    Metadata for all domain events in the Event-Driven Architecture.

    This follows Kafka-style event metadata with distributed tracing support.
    All metadata fields are optional except event_id, event_type, and timestamp.

    Attributes:
        event_id: Unique identifier for this event instance
        event_type: Type name of the event (e.g., "PluginRegistered")
        timestamp: When the event occurred (UTC)
        correlation_id: Links multiple events in a workflow
        causation_id: Links this event to the command that caused it
        user_id: Optional user who triggered the event
        trace_id: Distributed tracing ID for request tracking
    """

    event_id: UUID
    event_type: str
    timestamp: datetime
    correlation_id: Optional[UUID] = None
    causation_id: Optional[UUID] = None
    user_id: Optional[str] = None
    trace_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for serialization"""
        data = asdict(self)
        # Convert UUID to string
        data["event_id"] = str(self.event_id)
        if self.correlation_id:
            data["correlation_id"] = str(self.correlation_id)
        if self.causation_id:
            data["causation_id"] = str(self.causation_id)
        # Convert datetime to ISO format
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EventMetadata":
        """Create metadata from dictionary for deserialization"""
        return cls(
            event_id=UUID(data["event_id"]),
            event_type=data["event_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            correlation_id=UUID(data["correlation_id"]) if data.get("correlation_id") else None,
            causation_id=UUID(data["causation_id"]) if data.get("causation_id") else None,
            user_id=data.get("user_id"),
            trace_id=data.get("trace_id"),
        )


@dataclass
class Event:
    """
    Base class for all domain events in the Event-Driven Architecture.

    Events are immutable facts about something that happened in the system.
    They form the basis of Event Sourcing - the event log is the source of truth.

    Attributes:
        metadata: Event metadata (ID, type, timestamp, tracing)
        data: Event payload (domain-specific data)
    """

    metadata: EventMetadata
    data: Dict[str, Any]

    @property
    def event_type(self) -> str:
        """Get event type from metadata"""
        return self.metadata.event_type

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for serialization"""
        return {"metadata": self.metadata.to_dict(), "data": self.data}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary for deserialization"""
        return cls(metadata=EventMetadata.from_dict(data["metadata"]), data=data["data"])
