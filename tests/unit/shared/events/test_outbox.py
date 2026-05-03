from uuid import uuid4

import pytest

from src.shared.events.event import DomainEvent
from src.shared.events.outbox import OutboxMessage, OutboxRepository


class PluginRegistered(DomainEvent):
    """Example concrete event for testing"""

    def __init__(self, plugin_id: str):
        super().__init__()
        self.plugin_id = plugin_id


class TestOutboxMessage:
    """Test OutboxMessage data class"""

    def test_create_outbox_message(self):
        """Should create outbox message from event"""
        event = PluginRegistered(plugin_id="crypto")

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        assert message.event_id == event.event_id
        assert message.event_type == "PluginRegistered"
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
        event = PluginRegistered(plugin_id="crypto")

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
            event = PluginRegistered(plugin_id=f"plugin_{i}")

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
        event = PluginRegistered(plugin_id="crypto")

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        outbox_repo.save(message)
        outbox_repo.mark_as_published(message.id)

        # Verify status
        messages = outbox_repo.get_pending_messages(limit=10)
        assert len(messages) == 0

    def test_mark_as_failed(self, outbox_repo):
        """Should mark message as failed with error"""
        event = PluginRegistered(plugin_id="crypto")

        message = OutboxMessage.from_event(event=event, aggregate_type="Plugin", aggregate_id=uuid4())

        outbox_repo.save(message)
        outbox_repo.mark_as_failed(message.id, "Connection timeout")

        # Verify error recorded
        messages = outbox_repo.get_failed_messages(limit=10)
        assert len(messages) == 1
        assert messages[0].error_message == "Connection timeout"
