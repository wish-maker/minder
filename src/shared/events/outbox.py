import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import UUID, uuid4

from src.shared.events.event import Event


@dataclass
class OutboxMessage:
    """
    Outbox message for reliable event publishing.

    Ensures events are persisted atomically with business transactions
    before being published to message brokers.

    Attributes:
        id: Unique identifier for outbox message
        event_id: ID of the event
        event_type: Type of event
        payload: Event payload as dictionary
        status: Publishing status (pending, published, failed)
        aggregate_type: Optional aggregate type
        aggregate_id: Optional aggregate ID
        created_at: When message was created
        published_at: When successfully published
        retry_count: Number of retry attempts
        error_message: Error details if failed
    """

    id: UUID
    event_id: UUID
    event_type: str
    payload: dict
    status: str = "pending"
    aggregate_type: Optional[str] = None
    aggregate_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    published_at: Optional[datetime] = None
    retry_count: int = 0
    error_message: Optional[str] = None

    @classmethod
    def from_event(
        cls, event: Event, aggregate_type: Optional[str] = None, aggregate_id: Optional[UUID] = None
    ) -> "OutboxMessage":
        """
        Create outbox message from event.

        Args:
            event: Event to create message from
            aggregate_type: Optional aggregate type
            aggregate_id: Optional aggregate ID

        Returns:
            OutboxMessage instance
        """
        return cls(
            id=uuid4(),
            event_id=event.metadata.event_id,
            event_type=event.metadata.event_type,
            payload=event.data,
            status="pending",
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            created_at=datetime.now(),
        )


class OutboxRepository:
    """
    Repository for outbox pattern operations.

    Manages reliable event publishing by storing events atomically
    with business transactions, then publishing in background process.

    Attributes:
        db_session: Database session for operations
    """

    def __init__(self, db_session):
        """
        Initialize outbox repository.

        Args:
            db_session: Database session
        """
        self.db_session = db_session

    def save(self, message: OutboxMessage) -> None:
        """
        Save message to outbox.

        Args:
            message: OutboxMessage to save
        """
        query = """
            INSERT INTO outbox (
                id, event_id, event_type, payload, status,
                aggregate_type, aggregate_id, created_at,
                retry_count, error_message
            ) VALUES (
                :id, :event_id, :event_type, :payload, :status,
                :aggregate_type, :aggregate_id, :created_at,
                :retry_count, :error_message
            )
        """

        self.db_session.execute(
            query,
            {
                "id": str(message.id),
                "event_id": str(message.event_id),
                "event_type": message.event_type,
                "payload": json.dumps(message.payload),
                "status": message.status,
                "aggregate_type": message.aggregate_type,
                "aggregate_id": str(message.aggregate_id) if message.aggregate_id else None,
                "created_at": message.created_at,
                "retry_count": message.retry_count,
                "error_message": message.error_message,
            },
        )

    def get_pending_messages(self, limit: int = 100) -> List[OutboxMessage]:
        """
        Get pending messages for publishing.

        Args:
            limit: Maximum number of messages to retrieve

        Returns:
            List of pending OutboxMessage instances
        """
        query = """
            SELECT id, event_id, event_type, payload, status,
                   aggregate_type, aggregate_id, created_at,
                   published_at, retry_count, error_message
            FROM outbox
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT :limit
        """

        results = self.db_session.execute(query, {"limit": limit})

        messages = []
        for row in results:
            messages.append(
                OutboxMessage(
                    id=UUID(row[0]),
                    event_id=UUID(row[1]),
                    event_type=row[2],
                    payload=json.loads(row[3]),
                    status=row[4],
                    aggregate_type=row[5],
                    aggregate_id=UUID(row[6]) if row[6] else None,
                    created_at=row[7],
                    published_at=row[8],
                    retry_count=row[9],
                    error_message=row[10],
                )
            )

        return messages

    def mark_as_published(self, message_id: UUID) -> None:
        """
        Mark message as successfully published.

        Args:
            message_id: ID of message to mark
        """
        query = """
            UPDATE outbox
            SET status = 'published',
                published_at = NOW()
            WHERE id = :id
        """

        self.db_session.execute(query, {"id": str(message_id)})

    def mark_as_failed(self, message_id: UUID, error_message: str) -> None:
        """
        Mark message as failed with error details.

        Args:
            message_id: ID of message to mark
            error_message: Error description
        """
        query = """
            UPDATE outbox
            SET status = 'failed',
                error_message = :error_message,
                retry_count = retry_count + 1
            WHERE id = :id
        """

        self.db_session.execute(query, {"id": str(message_id), "error_message": error_message})

    def get_failed_messages(self, limit: int = 100) -> List[OutboxMessage]:
        """
        Get failed messages for retry.

        Args:
            limit: Maximum number of messages to retrieve

        Returns:
            List of failed OutboxMessage instances
        """
        query = """
            SELECT id, event_id, event_type, payload, status,
                   aggregate_type, aggregate_id, created_at,
                   published_at, retry_count, error_message
            FROM outbox
            WHERE status = 'failed'
            ORDER BY created_at ASC
            LIMIT :limit
        """

        results = self.db_session.execute(query, {"limit": limit})

        messages = []
        for row in results:
            messages.append(
                OutboxMessage(
                    id=UUID(row[0]),
                    event_id=UUID(row[1]),
                    event_type=row[2],
                    payload=json.loads(row[3]),
                    status=row[4],
                    aggregate_type=row[5],
                    aggregate_id=UUID(row[6]) if row[6] else None,
                    created_at=row[7],
                    published_at=row[8],
                    retry_count=row[9],
                    error_message=row[10],
                )
            )

        return messages
