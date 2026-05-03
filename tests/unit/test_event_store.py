# tests/unit/test_event_store.py

from uuid import uuid4

import pytest

from src.shared.events.event import DomainEvent
from src.shared.events.event_store import ConcurrencyException, EventStoreRepository


class MockEvent(DomainEvent):
    def __init__(self):
        self.event_id = uuid4()
        self.metadata = {}
        self.test_data = "test"


def test_append_events_success():
    """Test appending events to event store"""
    repo = EventStoreRepository("postgresql://minder:test@localhost/minder")
    repo.connect()

    aggregate_id = uuid4()

    # Append events
    events = [MockEvent(), MockEvent()]
    repo.append(aggregate_id, expected_version=0, events=events)

    # Verify events were stored
    stream = repo.get_stream(aggregate_id)
    assert len(stream) == 2

    # Verify outbox entries were created
    with repo._conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM outbox_events WHERE status = 'pending'
        """
        )
        count = cursor.fetchone()[0]
        assert count == 2


def test_optimistic_concurrency_conflict():
    """Test concurrent modification detection"""
    repo = EventStoreRepository("postgresql://minder:test@localhost/minder")
    repo.connect()

    aggregate_id = uuid4()

    # First append
    repo.append(aggregate_id, expected_version=0, events=[MockEvent()])

    # Try to append with wrong version (should fail)
    with pytest.raises(ConcurrencyException):
        repo.append(aggregate_id, expected_version=0, events=[MockEvent()])


def test_atomic_transaction_rollback():
    """Test that both event store and outbox rollback on error"""
    repo = EventStoreRepository("postgresql://minder:test@localhost/minder")
    repo.connect()

    aggregate_id = uuid4()

    # Create test event
    test_event = MockEvent()

    # Append with wrong version to trigger rollback
    try:
        repo.append(aggregate_id, expected_version=5, events=[test_event])
    except ConcurrencyException:
        pass

    # Verify neither event store nor outbox has the event
    stream = repo.get_stream(aggregate_id)
    assert len(stream) == 0

    with repo._conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT COUNT(*) FROM outbox_events
            WHERE event_id = %s
        """,
            (str(test_event.event_id),),
        )
        count = cursor.fetchone()[0]
        assert count == 0
