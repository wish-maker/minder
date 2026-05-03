import json
from typing import Any, Dict, List, Optional
from uuid import UUID

from src.shared.events.event import Event


class EventStore:
    """
    Repository for Event Sourcing persistence.

    Provides append-only event storage with snapshot support for
    efficient state reconstruction. Events are stored in PostgreSQL
    and indexed by aggregate for efficient retrieval.

    Attributes:
        db_session: Database session for PostgreSQL operations
    """

    def __init__(self, db_session):
        """
        Initialize event store.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db_session = db_session

    def append(self, event: Event, aggregate_type: str, aggregate_id: UUID, version: int) -> None:
        """
        Append event to event store.

        Args:
            event: Event to append
            aggregate_type: Type of aggregate (e.g., "Plugin")
            aggregate_id: Identifier of aggregate instance
            version: Version number for optimistic locking
        """
        query = """
            INSERT INTO events (
                event_id, event_type, timestamp,
                correlation_id, causation_id, user_id, trace_id,
                data, aggregate_type, aggregate_id, version
            ) VALUES (
                :event_id, :event_type, :timestamp,
                :correlation_id, :causation_id, :user_id, :trace_id,
                :data, :aggregate_type, :aggregate_id, :version
            )
        """

        self.db_session.execute(
            query,
            {
                "event_id": str(event.metadata.event_id),
                "event_type": event.metadata.event_type,
                "timestamp": event.metadata.timestamp,
                "correlation_id": str(event.metadata.correlation_id) if event.metadata.correlation_id else None,
                "causation_id": str(event.metadata.causation_id) if event.metadata.causation_id else None,
                "user_id": event.metadata.user_id,
                "trace_id": event.metadata.trace_id,
                "data": json.dumps(event.data),
                "aggregate_type": aggregate_type,
                "aggregate_id": str(aggregate_id),
                "version": version,
            },
        )

    def get_events(self, aggregate_type: str, aggregate_id: UUID, from_version: Optional[int] = None) -> List[Event]:
        """
        Retrieve events for an aggregate.

        Args:
            aggregate_type: Type of aggregate
            aggregate_id: Identifier of aggregate instance
            from_version: Optional starting version

        Returns:
            List of events in version order
        """
        query = """
            SELECT event_id, event_type, timestamp,
                   correlation_id, causation_id, user_id, trace_id,
                   data
            FROM events
            WHERE aggregate_type = :aggregate_type
              AND aggregate_id = :aggregate_id
        """

        params = {"aggregate_type": aggregate_type, "aggregate_id": str(aggregate_id)}

        if from_version:
            query += " AND version >= :from_version"
            params["from_version"] = from_version

        query += " ORDER BY version ASC"

        results = self.db_session.execute(query, params)

        events = []
        for row in results:
            from src.shared.events.event import EventMetadata

            metadata = EventMetadata(
                event_id=UUID(row[0]),
                event_type=row[1],
                timestamp=row[2],
                correlation_id=UUID(row[3]) if row[3] else None,
                causation_id=UUID(row[4]) if row[4] else None,
                user_id=row[5],
                trace_id=row[6],
            )

            event = Event(metadata=metadata, data=json.loads(row[7]))
            events.append(event)

        return events

    def save_snapshot(self, aggregate_type: str, aggregate_id: UUID, version: int, state: Dict[str, Any]) -> None:
        """
        Save aggregate snapshot.

        Args:
            aggregate_type: Type of aggregate
            aggregate_id: Identifier of aggregate instance
            version: Event version up to which snapshot applies
            state: Aggregate state as dictionary
        """
        query = """
            INSERT INTO snapshots (aggregate_type, aggregate_id, version, state)
            VALUES (:aggregate_type, :aggregate_id, :version, :state)
        """

        self.db_session.execute(
            query,
            {
                "aggregate_type": aggregate_type,
                "aggregate_id": str(aggregate_id),
                "version": version,
                "state": json.dumps(state),
            },
        )

    def get_latest_snapshot(self, aggregate_type: str, aggregate_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Get latest snapshot for an aggregate.

        Args:
            aggregate_type: Type of aggregate
            aggregate_id: Identifier of aggregate instance

        Returns:
            Snapshot dictionary with 'version' and 'state' keys, or None
        """
        query = """
            SELECT version, state
            FROM snapshots
            WHERE aggregate_type = :aggregate_type
              AND aggregate_id = :aggregate_id
            ORDER BY version DESC
            LIMIT 1
        """

        result = self.db_session.execute(
            query, {"aggregate_type": aggregate_type, "aggregate_id": str(aggregate_id)}
        ).fetchone()

        if not result:
            return None

        return {"version": result[0], "state": json.loads(result[1])}
