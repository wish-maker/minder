import io
import json
from typing import Any, Dict

import avro.io
from avro import schema as avro_schema
from avro.io import DatumReader, DatumWriter

from src.shared.events.event import Event


class AvroSerializer:
    """
    Avro serialization for events in the Event-Driven Architecture.

    Provides binary serialization with schema validation for efficient
    storage and transmission of events. Avro ensures type safety and
    enables schema evolution.

    Future enhancement: Integrate with Schema Registry for centralized
    schema management and compatibility validation.
    """

    def __init__(self):
        """Initialize serializer with Avro schema"""
        self._schema = self._build_schema()
        self._parsed_schema = avro_schema.parse(json.dumps(self._schema))

    def serialize(self, event: Event) -> bytes:
        """
        Serialize event to Avro binary format.

        Args:
            event: Event object to serialize

        Returns:
            Binary Avro data
        """
        # Convert event to dict format compatible with Avro
        # Encode data as JSON string to preserve types
        event_dict = {
            "metadata": {
                "event_id": str(event.metadata.event_id),
                "event_type": event.metadata.event_type,
                "timestamp": event.metadata.timestamp.isoformat(),
                "correlation_id": str(event.metadata.correlation_id) if event.metadata.correlation_id else None,
                "causation_id": str(event.metadata.causation_id) if event.metadata.causation_id else None,
                "user_id": event.metadata.user_id,
                "trace_id": event.metadata.trace_id,
            },
            "data": event.data,
        }

        # Write to Avro format
        writer = DatumWriter(self._parsed_schema)
        bytes_writer = io.BytesIO()
        encoder = avro.io.BinaryEncoder(bytes_writer)
        writer.write(event_dict, encoder)

        return bytes_writer.getvalue()

    def deserialize(self, data: bytes) -> Event:
        """
        Deserialize Avro bytes to Event object.

        Args:
            data: Binary Avro data

        Returns:
            Event object
        """
        from datetime import datetime
        from uuid import UUID

        from src.shared.events.event import EventMetadata

        reader = DatumReader(self._parsed_schema)
        bytes_reader = io.BytesIO(data)
        decoder = avro.io.BinaryDecoder(bytes_reader)
        event_dict = reader.read(decoder)

        # Reconstruct Event object
        metadata = EventMetadata(
            event_id=UUID(event_dict["metadata"]["event_id"]),
            event_type=event_dict["metadata"]["event_type"],
            timestamp=datetime.fromisoformat(event_dict["metadata"]["timestamp"]),
            correlation_id=(
                UUID(event_dict["metadata"]["correlation_id"]) if event_dict["metadata"]["correlation_id"] else None
            ),
            causation_id=(
                UUID(event_dict["metadata"]["causation_id"]) if event_dict["metadata"]["causation_id"] else None
            ),
            user_id=event_dict["metadata"]["user_id"],
            trace_id=event_dict["metadata"]["trace_id"],
        )

        # Data is already deserialized as dict from Avro
        return Event(metadata=metadata, data=event_dict["data"])

    def get_schema(self) -> Dict[str, Any]:
        """
        Get the Avro schema for Event type.

        Returns:
            Avro schema as dictionary
        """
        return self._schema

    def validate(self, event: Event) -> None:
        """
        Validate event against Avro schema.

        Args:
            event: Event to validate

        Raises:
            ValueError: If event doesn't match schema
        """
        # For now, serialize acts as validation
        # In production, would use Schema Registry
        try:
            self.serialize(event)
        except Exception as e:
            raise ValueError(f"Event validation failed: {e}")

    def _build_schema(self) -> Dict[str, Any]:
        """
        Build Avro schema for Event type.

        Returns:
            Avro schema dictionary
        """
        return {
            "type": "record",
            "name": "Event",
            "namespace": "minder.events",
            "doc": "Base event type for Minder Event-Driven Architecture",
            "fields": [
                {
                    "name": "metadata",
                    "type": {
                        "type": "record",
                        "name": "EventMetadata",
                        "fields": [
                            {"name": "event_id", "type": "string"},
                            {"name": "event_type", "type": "string"},
                            {"name": "timestamp", "type": "string"},
                            {"name": "correlation_id", "type": ["null", "string"], "default": None},
                            {"name": "causation_id", "type": ["null", "string"], "default": None},
                            {"name": "user_id", "type": ["null", "string"], "default": None},
                            {"name": "trace_id", "type": ["null", "string"], "default": None},
                        ],
                    },
                },
                {"name": "data", "type": {"type": "map", "values": "string"}},
            ],
        }
