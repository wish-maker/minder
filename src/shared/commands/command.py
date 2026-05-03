from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID


@dataclass
class CommandMetadata:
    """
    Metadata for all commands in the CQRS architecture.

    Commands represent intents to change state. They are imperatives
    that will result in events being generated if successful.

    Attributes:
        command_id: Unique identifier for this command instance
        command_type: Type name of the command (e.g., "RegisterPlugin")
        timestamp: When the command was issued (UTC)
        user_id: Optional user who issued the command
        correlation_id: Links multiple commands/events in a workflow
    """

    command_id: UUID
    command_type: str
    timestamp: datetime
    user_id: Optional[str] = None
    correlation_id: Optional[UUID] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary for serialization"""
        data = asdict(self)
        # Convert UUID to string
        data["command_id"] = str(self.command_id)
        if self.correlation_id:
            data["correlation_id"] = str(self.correlation_id)
        # Convert datetime to ISO format
        data["timestamp"] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandMetadata":
        """Create metadata from dictionary for deserialization"""
        return cls(
            command_id=UUID(data["command_id"]),
            command_type=data["command_type"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            user_id=data.get("user_id"),
            correlation_id=UUID(data["correlation_id"]) if data.get("correlation_id") else None,
        )


@dataclass
class Command:
    """
    Base class for all commands in the CQRS architecture.

    Commands represent intents to change state. They are validated,
    executed, and if successful, result in events being generated.

    Attributes:
        metadata: Command metadata (ID, type, timestamp, user)
        data: Command payload (domain-specific data)
    """

    metadata: CommandMetadata
    data: Dict[str, Any]

    @property
    def command_type(self) -> str:
        """Get command type from metadata"""
        return self.metadata.command_type

    def to_dict(self) -> Dict[str, Any]:
        """Convert command to dictionary for serialization"""
        return {"metadata": self.metadata.to_dict(), "data": self.data}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Command":
        """Create command from dictionary for deserialization"""
        return cls(metadata=CommandMetadata.from_dict(data["metadata"]), data=data["data"])
