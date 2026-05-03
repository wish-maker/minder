# src/shared/events/avro_serializer.py

import json
from datetime import datetime
from io import BytesIO
from typing import Any, Dict
from uuid import UUID

import avro.schema

from src.shared.events.event import DomainEvent


class AvroEventSerializer:
    """Serialize events using Avro format"""

    def __init__(self, schema_registry_url: str = "http://localhost:8082"):
        self.schema_registry_url = schema_registry_url
        self._schemas: Dict[str, avro.schema.Schema] = {}

    def serialize(self, event: DomainEvent) -> bytes:
        """Serialize event to Avro binary format"""
        # Get or create schema
        schema = self._get_or_create_schema(event)

        # Create Avro record writer
        writer = avro.io.DatumWriter(schema)

        # Convert event to dict
        event_dict = self._event_to_dict(event)

        # Write to bytes
        bytes_io = BytesIO()
        writer.write(bytes_io, event_dict)

        return bytes_io.getvalue()

    def deserialize(self, data: bytes, event_type: str) -> DomainEvent:
        """Deserialize Avro binary to event"""
        schema = self._schemas.get(event_type)
        if not schema:
            raise ValueError(f"Unknown event type: {event_type}")

        reader = avro.io.DatumReader(schema)
        bytes_io = BytesIO(data)
        event_dict = reader.read(bytes_io)

        return self._dict_to_event(event_dict, event_type)

    def _get_or_create_schema(self, event: DomainEvent) -> avro.schema.Schema:
        """Get or register Avro schema for event type"""
        event_type = event.__class__.__name__

        if event_type not in self._schemas:
            # Create Avro schema from event structure
            schema = avro.schema.Parse(
                json.dumps({"type": "record", "name": event_type, "fields": self._infer_fields(event)})
            )

            self._schemas[event_type] = schema

            # Register in Apicurio Registry
            # (Implementation would call registry API)

        return self._schemas[event_type]

    def _infer_fields(self, event: DomainEvent) -> list:
        """Infer Avro fields from event dataclass"""
        fields = []
        for key, value in event.__dict__.items():
            if key == "metadata":
                continue

            avro_type = "string"
            if isinstance(value, int):
                avro_type = "long"
            elif isinstance(value, float):
                avro_type = "double"
            elif isinstance(value, bool):
                avro_type = "boolean"
            elif isinstance(value, list):
                avro_type = {"type": "array", "items": "string"}
            elif isinstance(value, dict):
                avro_type = {"type": "map", "values": "string"}
            elif isinstance(value, UUID):
                avro_type = "string"

            fields.append({"name": key, "type": [avro_type, "null"] if value is None else avro_type})

        return fields

    def _event_to_dict(self, event: DomainEvent) -> Dict[str, Any]:
        """Convert event to dictionary for Avro"""
        result = {}
        for key, value in event.__dict__.items():
            if key == "metadata":
                continue
            if isinstance(value, (UUID, datetime)):
                result[key] = str(value)
            elif hasattr(value, "value"):
                result[key] = value.value
            else:
                result[key] = value
        return result

    def _dict_to_event(self, data: Dict, event_type: str) -> DomainEvent:
        """Convert dictionary back to event (placeholder)"""
        # Implementation would use event registry
        pass
