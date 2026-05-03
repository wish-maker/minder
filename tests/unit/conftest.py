"""
Unit test configuration for Minder services.
Provides fixtures for unit tests without external dependencies.
"""

from unittest.mock import MagicMock

import pytest


class MockDBResult:
    """Mock database result that supports iteration"""

    def __init__(self, rows=None):
        self.rows = rows or []

    def __iter__(self):
        return iter(self.rows)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


@pytest.fixture(scope="function")
def db_session():
    """
    Mock database session for unit tests.

    Provides a mock SQLAlchemy session that can be used to test
    database operations without requiring an actual database connection.

    The session stores data in memory during the test, allowing for
    realistic testing of CRUD operations.
    """
    session = MagicMock()

    # In-memory storage for events and snapshots
    event_storage = []
    snapshot_storage = []

    def mock_execute(query, params=None):
        """Mock execute that stores and retrieves data"""
        query_str = query.lower() if isinstance(query, str) else str(query)

        # INSERT INTO events
        if "insert into events" in query_str:
            event_storage.append(params)
            return MockDBResult([])

        # INSERT INTO snapshots
        elif "insert into snapshots" in query_str:
            snapshot_storage.append(params)
            return MockDBResult([])

        # SELECT from events
        elif "select" in query_str and "from events" in query_str:
            # Filter by aggregate_type and aggregate_id
            filtered_events = [
                e
                for e in event_storage
                if e.get("aggregate_type") == params.get("aggregate_type")
                and e.get("aggregate_id") == params.get("aggregate_id")
            ]

            # Filter by from_version if specified
            if params.get("from_version"):
                filtered_events = [e for e in filtered_events if e.get("version", 0) >= params.get("from_version")]

            # Sort by version
            filtered_events.sort(key=lambda x: x.get("version", 0))

            # Convert to row format (event_id, event_type, timestamp, ...)
            rows = []
            for event in filtered_events:
                rows.append(
                    (
                        event["event_id"],
                        event["event_type"],
                        event["timestamp"],
                        event.get("correlation_id"),
                        event.get("causation_id"),
                        event.get("user_id"),
                        event.get("trace_id"),
                        event["data"],
                    )
                )
            return MockDBResult(rows)

        # SELECT from snapshots
        elif "select" in query_str and "from snapshots" in query_str:
            # Filter by aggregate_type and aggregate_id
            filtered_snapshots = [
                s
                for s in snapshot_storage
                if s.get("aggregate_type") == params.get("aggregate_type")
                and s.get("aggregate_id") == params.get("aggregate_id")
            ]

            # Sort by version descending and get latest
            filtered_snapshots.sort(key=lambda x: x.get("version", 0), reverse=True)

            if filtered_snapshots:
                snapshot = filtered_snapshots[0]
                rows = [(snapshot["version"], snapshot["state"])]
            else:
                rows = []

            return MockDBResult(rows)

        return MockDBResult([])

    session.execute = mock_execute

    return session
