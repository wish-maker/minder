# tests/unit/marketplace/test_events.py

from datetime import datetime, timezone
from uuid import uuid4

from src.marketplace.domain.events.marketplace_events import (
    LicenseExpired,
    LicensePurchased,
    PluginDelisted,
    PluginListed,
)


def test_plugin_listed_event_creation():
    """Test PluginListed event creation"""
    plugin_id = uuid4()
    developer_id = uuid4()

    event = PluginListed(
        plugin_id=plugin_id,
        plugin_name="Test Plugin",
        developer_id=developer_id,
        category="productivity",
        price=9.99,
        description="A test plugin",
        listing_date=datetime.now(timezone.utc),
    )

    assert event.plugin_id == plugin_id
    assert event.plugin_name == "Test Plugin"
    assert event.developer_id == developer_id
    assert event.category == "productivity"
    assert event.price == 9.99
    assert event.description == "A test plugin"
    assert isinstance(event.listing_date, datetime)


def test_license_purchased_event_creation():
    """Test LicensePurchased event creation"""
    license_id = uuid4()
    plugin_id = uuid4()
    user_id = uuid4()

    event = LicensePurchased(
        license_id=license_id,
        plugin_id=plugin_id,
        user_id=user_id,
        license_type="STANDARD",
        expiry_date=None,
        purchase_date=datetime.now(timezone.utc),
    )

    assert event.license_id == license_id
    assert event.plugin_id == plugin_id
    assert event.user_id == user_id
    assert event.license_type == "STANDARD"
    assert event.expiry_date is None


def test_plugin_delisted_event_creation():
    """Test PluginDelisted event creation"""
    plugin_id = uuid4()
    delisted_by = uuid4()

    event = PluginDelisted(
        plugin_id=plugin_id, reason="Policy violation", delisted_by=delisted_by, delisted_at=datetime.now(timezone.utc)
    )

    assert event.plugin_id == plugin_id
    assert event.reason == "Policy violation"
    assert event.delisted_by == delisted_by
    assert isinstance(event.delisted_at, datetime)


def test_all_events_inherit_from_domain_event():
    """Test all events inherit from DomainEvent base class"""
    from src.shared.events.event import DomainEvent

    plugin_id = uuid4()

    events = [
        PluginListed(
            plugin_id=plugin_id,
            plugin_name="Test",
            developer_id=uuid4(),
            category="test",
            price=0.0,
            description=None,
            listing_date=datetime.now(timezone.utc),
        ),
        LicensePurchased(
            license_id=uuid4(),
            plugin_id=plugin_id,
            user_id=uuid4(),
            license_type="TRIAL",
            expiry_date=None,
            purchase_date=datetime.now(timezone.utc),
        ),
        LicenseExpired(
            license_id=uuid4(), plugin_id=plugin_id, user_id=uuid4(), expiry_date=datetime.now(timezone.utc)
        ),
        PluginDelisted(plugin_id=plugin_id, reason="test", delisted_by=uuid4(), delisted_at=datetime.now(timezone.utc)),
    ]

    for event in events:
        assert isinstance(event, DomainEvent)
        assert hasattr(event, "event_id")
        assert hasattr(event, "metadata")
