from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.shared.events.event import Event, EventMetadata
from src.shared.events.outbox import OutboxMessage, OutboxRepository


class TestOutboxMessage:
    """Test OutboxMessage data class"""

    def test_create_outbox_message(self):
        """Should create outbox message from event"""
        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto"},
        )

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        assert message.event_id == event.metadata.event_id
        assert message.event_type == "PluginRegistered"
        assert message.payload == event.data
        assert message.status == "pending"
        assert message.retry_count == 0


class TestOutboxRepository:
    """Test OutboxRepository operations"""

    @pytest.fixture
    def outbox_repo(self, db_session):
        """Create outbox repository"""
        return OutboxRepository(db_session)

    def test_save_message(self, outbox_repo):
        """Should save message to outbox"""
        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto"},
        )

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        outbox_repo.save(message)

        # Verify saved
        messages = outbox_repo.get_pending_messages(limit=10)
        assert len(messages) == 1
        assert messages[0].event_type == "PluginRegistered"

    def test_get_pending_messages(self, outbox_repo):
        """Should retrieve only pending messages"""
        # Create 3 pending, 2 published
        for i in range(5):
            event = Event(
                metadata=EventMetadata(event_id=uuid4(), event_type=f"Event{i}", timestamp=datetime.now(timezone.utc)),
                data={"index": i},
            )

            message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

            outbox_repo.save(message)

            # Mark first 2 as published
            if i < 2:
                outbox_repo.mark_as_published(message.id)

        # Get pending
        pending = outbox_repo.get_pending_messages(limit=10)
        assert len(pending) == 3

    def test_mark_as_published(self, outbox_repo):
        """Should mark message as published"""
        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto"},
        )

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        outbox_repo.save(message)
        outbox_repo.mark_as_published(message.id)

        # Verify status
        messages = outbox_repo.get_pending_messages(limit=10)
        assert len(messages) == 0

    def test_mark_as_failed(self, outbox_repo):
        """Should mark message as failed with error"""
        event = Event(
            metadata=EventMetadata(
                event_id=uuid4(), event_type="PluginRegistered", timestamp=datetime.now(timezone.utc)
            ),
            data={"plugin_id": "crypto"},
        )

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        outbox_repo.save(message)
        outbox_repo.mark_as_failed(message.id, "Connection timeout")

        # Verify error recorded
        messages = outbox_repo.get_failed_messages(limit=10)
        assert len(messages) == 1
        assert messages[0].error_message == "Connection timeout"
