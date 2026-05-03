# src/shared/events/event_store.py

import json
import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_READ_COMMITTED

from src.shared.events.event import DomainEvent

logger = logging.getLogger(__name__)


class ConcurrencyException(Exception):
    """Raised when optimistic concurrency check fails"""

    pass


class EventStoreRepository:
    """
    PostgreSQL-based Event Store with optimistic concurrency.
    This is the shared repository used by all aggregates.

    CRITICAL: Every append() operation writes to BOTH minder_events and outbox_events
    in the SAME transaction for reliable event publishing.
    """

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._conn = None

    def connect(self):
        """Establish database connection"""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.connection_string)
            self._conn.set_isolation_level(ISOLATION_LEVEL_READ_COMMITTED)

    def append(self, aggregate_id: UUID, expected_version: int, events: List[DomainEvent]) -> None:
        """
        Append events with optimistic concurrency control.

        CRITICAL: This method writes to BOTH minder_events and outbox_events
        in a SINGLE transaction. This guarantees that if an event is stored,
        it's also in the outbox for reliable publishing.

        Args:
            aggregate_id: Aggregate identifier
            expected_version: Expected current version (for concurrency check)
            events: List of events to append

        Raises:
            ConcurrencyException: If version mismatch (concurrent modification)
        """
        self.connect()

        try:
            with self._conn.cursor() as cursor:
                # Check current version (FOR UPDATE lock)
                cursor.execute(
                    """
                    SELECT COALESCE(MAX(aggregate_version), 0) as current_version
                    FROM minder_events
                    WHERE aggregate_id = %s
                    FOR UPDATE
                """,
                    (str(aggregate_id),),
                )

                result = cursor.fetchone()
                current_version = result[0] if result else 0

                # Validate version (OPTIMISTIC CONCURRENCY)
                if current_version != expected_version:
                    raise ConcurrencyException(
                        f"Version conflict for aggregate {aggregate_id}: "
                        f"expected {expected_version}, found {current_version}"
                    )

                # Insert events ATOMICALLY with outbox entries
                for version_offset, event in enumerate(events, start=1):
                    event_dict = self._serialize_event(event)
                    new_version = current_version + version_offset

                    # 1. Insert into event store
                    cursor.execute(
                        """
                        INSERT INTO minder_events (
                            aggregate_id,
                            aggregate_version,
                            event_type,
                            payload,
                            extra_metadata
                        ) VALUES (%s, %s, %s, %s, %s)
                    """,
                        (
                            str(aggregate_id),
                            new_version,
                            event.__class__.__name__,
                            json.dumps(event_dict["payload"]),
                            json.dumps(event_dict.get("extra_metadata", {})),
                        ),
                    )

                    # 2. Insert into outbox (SAME TRANSACTION)
                    # This guarantees reliable event publishing
                    cursor.execute(
                        """
                        INSERT INTO outbox_events (
                            event_id,
                            event_type,
                            payload,
                            extra_metadata,
                            status
                        ) VALUES (%s, %s, %s, %s, %s)
                    """,
                        (
                            str(event.event_id),
                            event.__class__.__name__,
                            json.dumps(event_dict["payload"]),
                            json.dumps(event_dict.get("extra_metadata", {})),
                            "pending",
                        ),
                    )

                    logger.debug(
                        f"Appended event {event.__class__.__name__} "
                        f"to aggregate {aggregate_id} version {new_version} "
                        f"with outbox entry"
                    )

                # ATOMIC COMMIT - both event store and outbox written together
                self._conn.commit()

                logger.info(
                    f"Appended {len(events)} events to aggregate {aggregate_id}, "
                    f"versions {current_version + 1} to {current_version + len(events)}"
                )

        except psycopg2.IntegrityError as e:
            self._conn.rollback()
            raise ConcurrencyException(f"Concurrent modification detected for aggregate {aggregate_id}") from e
        except psycopg2.Error as e:
            self._conn.rollback()
            logger.error(f"Database error in append: {e}")
            raise

    def get_stream(self, aggregate_id: UUID, from_version: Optional[int] = None) -> List[DomainEvent]:
        """Load event stream for aggregate"""
        self.connect()

        try:
            with self._conn.cursor() as cursor:
                if from_version is None:
                    cursor.execute(
                        """
                        SELECT event_type, payload, extra_metadata
                        FROM minder_events
                        WHERE aggregate_id = %s
                        ORDER BY aggregate_version ASC
                    """,
                        (str(aggregate_id),),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT event_type, payload, extra_metadata
                        FROM minder_events
                        WHERE aggregate_id = %s AND aggregate_version > %s
                        ORDER BY aggregate_version ASC
                    """,
                        (str(aggregate_id), from_version),
                    )

                events = []
                for row in cursor.fetchall():
                    event = self._deserialize_event(row)
                    events.append(event)

                return events

        except psycopg2.Error as e:
            logger.error(f"Database error in get_stream: {e}")
            raise

    def _serialize_event(self, event: DomainEvent) -> dict:
        """Serialize event to dictionary"""
        payload = {}
        for key, value in event.__dict__.items():
            if key not in ["event_id", "metadata"]:
                if isinstance(value, (UUID, datetime)):
                    payload[key] = str(value)
                elif hasattr(value, "value"):
                    payload[key] = value.value
                else:
                    payload[key] = value

        return {"payload": payload, "extra_metadata": event.metadata}

    def _deserialize_event(self, row) -> DomainEvent:
        """Deserialize event from database row"""
        # Implementation would use event registry
        # For now, return placeholder
        pass
