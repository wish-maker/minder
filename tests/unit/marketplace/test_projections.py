# tests/unit/marketplace/test_projections.py

from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest

from src.marketplace.projections.marketplace_projection_handler import MarketplaceProjectionHandler


@pytest.fixture
def marketplace_handler():
    """Create a MarketplaceProjectionHandler for testing"""
    handler = MarketplaceProjectionHandler(
        pg_url="postgresql://test", redis_url="redis://localhost", rabbitmq_url="amqp://localhost"
    )

    # Mock connections to prevent real connection attempts
    handler._pg_conn = Mock()
    handler._redis_client = Mock()

    # Patch connect method to do nothing
    handler.connect = Mock()

    return handler


def test_pluginlisted_updates_postgres_and_redis(marketplace_handler):
    """Test PluginListed updates both PostgreSQL and Redis"""
    # Mock cursor context manager
    mock_cursor = Mock()
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__ = Mock(return_value=mock_cursor)
    mock_context_manager.__exit__ = Mock(return_value=False)
    marketplace_handler._pg_conn.cursor.return_value = mock_context_manager

    event_data = {
        "plugin_id": uuid4(),
        "plugin_name": "Test Plugin",
        "developer_id": uuid4(),
        "category": "productivity",
        "price": 9.99,
        "description": "Test description",
        "listing_date": datetime.now(timezone.utc),
    }

    marketplace_handler._handle_pluginlisted(event_data, is_replay=False)

    # Verify PostgreSQL execute was called
    assert mock_cursor.execute.called

    # Verify PostgreSQL commit was called
    assert marketplace_handler._pg_conn.commit.called

    # Verify Redis setex was called
    assert marketplace_handler._redis_client.setex.called


def test_plugindelisted_updates_postgres_and_invalidates_redis(marketplace_handler):
    """Test PluginDelisted updates PostgreSQL and invalidates Redis cache"""
    # Mock cursor context manager
    mock_cursor = Mock()
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__ = Mock(return_value=mock_cursor)
    mock_context_manager.__exit__ = Mock(return_value=False)
    marketplace_handler._pg_conn.cursor.return_value = mock_context_manager

    event_data = {
        "plugin_id": uuid4(),
        "reason": "Policy violation",
        "delisted_by": uuid4(),
        "delisted_at": datetime.now(timezone.utc),
    }

    marketplace_handler._handle_plugindelisted(event_data, is_replay=False)

    # Verify PostgreSQL execute was called
    assert mock_cursor.execute.called

    # Verify PostgreSQL commit was called
    assert marketplace_handler._pg_conn.commit.called

    # Verify Redis delete was called to invalidate cache
    assert marketplace_handler._redis_client.delete.called


def test_licensepurchased_creates_license_record(marketplace_handler):
    """Test LicensePurchased creates license projection"""
    # Mock cursor context manager
    mock_cursor = Mock()
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__ = Mock(return_value=mock_cursor)
    mock_context_manager.__exit__ = Mock(return_value=False)
    marketplace_handler._pg_conn.cursor.return_value = mock_context_manager

    event_data = {
        "license_id": uuid4(),
        "plugin_id": uuid4(),
        "user_id": uuid4(),
        "license_type": "STANDARD",
        "expiry_date": datetime.now(timezone.utc),
        "purchase_date": datetime.now(timezone.utc),
    }

    marketplace_handler._handle_licensepurchased(event_data, is_replay=False)

    # Verify PostgreSQL execute was called
    assert mock_cursor.execute.called

    # Verify PostgreSQL commit was called
    assert marketplace_handler._pg_conn.commit.called

    # Verify Redis setex was called
    assert marketplace_handler._redis_client.setex.called


def test_licenseexpired_marks_license_as_expired(marketplace_handler):
    """Test LicenseExpired marks license as expired"""
    # Mock cursor context manager
    mock_cursor = Mock()
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__ = Mock(return_value=mock_cursor)
    mock_context_manager.__exit__ = Mock(return_value=False)
    marketplace_handler._pg_conn.cursor.return_value = mock_context_manager

    event_data = {
        "license_id": uuid4(),
        "plugin_id": uuid4(),
        "user_id": uuid4(),
        "expiry_date": datetime.now(timezone.utc),
    }

    marketplace_handler._handle_licenseexpired(event_data, is_replay=False)

    # Verify PostgreSQL execute was called
    assert mock_cursor.execute.called

    # Verify PostgreSQL commit was called
    assert marketplace_handler._pg_conn.commit.called

    # Verify Redis delete was called to invalidate cache
    assert marketplace_handler._redis_client.delete.called


def test_handler_rollback_on_error(marketplace_handler):
    """Test that handler rolls back transaction on error"""
    # Mock cursor to raise exception
    mock_cursor = Mock()
    mock_context_manager = MagicMock()
    mock_context_manager.__enter__ = Mock(return_value=mock_cursor)
    mock_context_manager.__exit__ = Mock(return_value=False)
    marketplace_handler._pg_conn.cursor.return_value = mock_context_manager

    mock_cursor.execute.side_effect = Exception("Database error")

    event_data = {
        "plugin_id": uuid4(),
        "plugin_name": "Test Plugin",
        "developer_id": uuid4(),
        "category": "productivity",
        "price": 9.99,
        "description": "Test",
        "listing_date": datetime.now(timezone.utc),
    }

    with pytest.raises(Exception, match="Database error"):
        marketplace_handler._handle_pluginlisted(event_data, is_replay=False)

    # Verify rollback was called
    assert marketplace_handler._pg_conn.rollback.called


def test_routing_keys_defined():
    """Test that routing keys are properly defined"""
    handler = MarketplaceProjectionHandler(
        pg_url="postgresql://test", redis_url="redis://localhost", rabbitmq_url="amqp://localhost"
    )

    expected_keys = [
        "marketplace.pluginlisted",
        "marketplace.plugindelisted",
        "marketplace.licensepurchased",
        "marketplace.licenseexpired",
    ]

    assert handler.routing_keys == expected_keys
