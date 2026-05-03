# tests/unit/marketplace/test_marketplace_aggregate.py

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.marketplace.domain.aggregates.marketplace_aggregate import MarketplaceAggregate, PluginStatus
from src.marketplace.domain.commands.marketplace_commands import (
    DelistPluginCommand,
    ListPluginCommand,
    PurchaseLicenseCommand,
)


class TestPluginListing:
    """Test plugin listing functionality"""

    def test_plugin_listing_happy_path(self):
        """Test successful plugin listing flow"""
        plugin_id = uuid4()
        developer_id = uuid4()

        command = ListPluginCommand(
            plugin_id=plugin_id,
            plugin_name="Test Plugin",
            developer_id=developer_id,
            category="productivity",
            price=9.99,
            description="A test plugin",
        )

        aggregate = MarketplaceAggregate(plugin_id)
        aggregate.list_plugin(command)

        # Verify event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1
        assert events[0].event_type == "PluginListed"

        # Verify state was updated
        assert aggregate.status == PluginStatus.LISTED
        assert aggregate.plugin_name == "Test Plugin"
        assert aggregate.category == "productivity"
        assert aggregate.price == 9.99
        assert aggregate.description == "A test plugin"

    def test_cannot_list_already_listed_plugin(self):
        """Test that listed plugin cannot be listed again"""
        plugin_id = uuid4()
        developer_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        # First listing
        command = ListPluginCommand(
            plugin_id=plugin_id,
            plugin_name="Test Plugin",
            developer_id=developer_id,
            category="productivity",
            price=9.99,
        )
        aggregate.list_plugin(command)

        # Try to list again (should fail)
        with pytest.raises(ValueError, match="Plugin already listed"):
            aggregate.list_plugin(command)

    def test_plugin_listing_without_description(self):
        """Test plugin listing with optional description"""
        plugin_id = uuid4()
        developer_id = uuid4()

        command = ListPluginCommand(
            plugin_id=plugin_id,
            plugin_name="Test Plugin",
            developer_id=developer_id,
            category="productivity",
            price=9.99,
            description=None,
        )

        aggregate = MarketplaceAggregate(plugin_id)
        aggregate.list_plugin(command)

        # Verify state
        assert aggregate.status == PluginStatus.LISTED
        assert aggregate.description is None


class TestPluginDelisting:
    """Test plugin delisting functionality"""

    def test_plugin_delisting_happy_path(self):
        """Test successful plugin delisting flow"""
        plugin_id = uuid4()
        developer_id = uuid4()
        delisted_by = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        # First list the plugin
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test Plugin",
                developer_id=developer_id,
                category="productivity",
                price=9.99,
            )
        )

        # Clear uncommitted events
        aggregate.mark_events_as_committed()

        # Now delist
        command = DelistPluginCommand(plugin_id=plugin_id, reason="Policy violation", delisted_by=delisted_by)
        aggregate.delist_plugin(command)

        # Verify state
        assert aggregate.status == PluginStatus.DELISTED

        # Verify event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1
        assert events[0].event_type == "PluginDelisted"
        assert events[0].data["reason"] == "Policy violation"

    def test_cannot_delist_unlisted_plugin(self):
        """Test that unlisted plugin cannot be delisted"""
        plugin_id = uuid4()
        delisted_by = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        command = DelistPluginCommand(plugin_id=plugin_id, reason="Test", delisted_by=delisted_by)

        with pytest.raises(ValueError, match="Plugin not listed"):
            aggregate.delist_plugin(command)

    def test_cannot_delist_already_delisted_plugin(self):
        """Test that delisted plugin cannot be delisted again"""
        plugin_id = uuid4()
        developer_id = uuid4()
        delisted_by = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        # List then delist
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test Plugin",
                developer_id=developer_id,
                category="productivity",
                price=9.99,
            )
        )
        aggregate.mark_events_as_committed()

        aggregate.delist_plugin(DelistPluginCommand(plugin_id=plugin_id, reason="Test", delisted_by=delisted_by))
        aggregate.mark_events_as_committed()

        # Try to delist again (should fail)
        with pytest.raises(ValueError, match="Plugin not listed"):
            aggregate.delist_plugin(DelistPluginCommand(plugin_id=plugin_id, reason="Test", delisted_by=delisted_by))


class TestLicensePurchase:
    """Test license purchase functionality"""

    def test_license_purchase_happy_path(self):
        """Test successful license purchase flow"""
        plugin_id = uuid4()
        developer_id = uuid4()
        user_id = uuid4()
        license_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        # First list the plugin
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test Plugin",
                developer_id=developer_id,
                category="productivity",
                price=9.99,
            )
        )
        aggregate.mark_events_as_committed()

        # Purchase license
        command = PurchaseLicenseCommand(
            license_id=license_id,
            plugin_id=plugin_id,
            user_id=user_id,
            license_type="STANDARD",
            expiry_days=365,
        )

        aggregate.purchase_license(command)

        # Verify event was created
        events = aggregate.get_uncommitted_events()
        assert len(events) == 1
        assert events[0].event_type == "LicensePurchased"
        assert events[0].data["license_type"] == "STANDARD"

    def test_cannot_purchase_license_for_unlisted_plugin(self):
        """Test that license cannot be purchased for unlisted plugin"""
        plugin_id = uuid4()
        user_id = uuid4()
        license_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        command = PurchaseLicenseCommand(
            license_id=license_id,
            plugin_id=plugin_id,
            user_id=user_id,
            license_type="STANDARD",
        )

        with pytest.raises(ValueError, match="Cannot purchase license for unlisted plugin"):
            aggregate.purchase_license(command)

    def test_license_purchase_with_trial_type(self):
        """Test license purchase with TRIAL type"""
        plugin_id = uuid4()
        developer_id = uuid4()
        user_id = uuid4()
        license_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test Plugin",
                developer_id=developer_id,
                category="productivity",
                price=0.0,
            )
        )
        aggregate.mark_events_as_committed()

        command = PurchaseLicenseCommand(
            license_id=license_id,
            plugin_id=plugin_id,
            user_id=user_id,
            license_type="TRIAL",
            expiry_days=30,
        )

        aggregate.purchase_license(command)

        events = aggregate.get_uncommitted_events()
        assert events[0].data["license_type"] == "TRIAL"


class TestUncommittedEventsManagement:
    """Test uncommitted events list management (CRITICAL for Projections)"""

    def test_uncommitted_events_initially_empty(self):
        """Test that new aggregate has no uncommitted events"""
        plugin_id = uuid4()
        aggregate = MarketplaceAggregate(plugin_id)

        assert len(aggregate.get_uncommitted_events()) == 0

    def test_list_plugin_creates_uncommitted_event(self):
        """Test that listing plugin creates uncommitted event"""
        plugin_id = uuid4()
        developer_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test",
                developer_id=developer_id,
                category="test",
                price=0.0,
            )
        )

        events = aggregate.get_uncommitted_events()
        assert len(events) == 1
        assert events[0].event_type == "PluginListed"

    def test_mark_as_committed_clears_events(self):
        """Test that mark_events_as_committed clears the list"""
        plugin_id = uuid4()
        developer_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test",
                developer_id=developer_id,
                category="test",
                price=0.0,
            )
        )

        # Has uncommitted event
        assert len(aggregate.get_uncommitted_events()) == 1

        # Mark as committed
        aggregate.mark_events_as_committed()

        # Now empty
        assert len(aggregate.get_uncommitted_events()) == 0

    def test_multiple_operations_accumulate_events(self):
        """Test that multiple operations accumulate uncommitted events"""
        plugin_id = uuid4()
        developer_id = uuid4()
        user_id = uuid4()
        license_id = uuid4()
        delisted_by = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        # List plugin
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test",
                developer_id=developer_id,
                category="test",
                price=0.0,
            )
        )

        # Purchase license
        aggregate.purchase_license(
            PurchaseLicenseCommand(
                license_id=license_id,
                plugin_id=plugin_id,
                user_id=user_id,
                license_type="TRIAL",
                expiry_days=30,
            )
        )

        # Delist plugin
        aggregate.delist_plugin(DelistPluginCommand(plugin_id=plugin_id, reason="Test", delisted_by=delisted_by))

        # Should have 3 uncommitted events
        events = aggregate.get_uncommitted_events()
        assert len(events) == 3
        assert events[0].event_type == "PluginListed"
        assert events[1].event_type == "LicensePurchased"
        assert events[2].event_type == "PluginDelisted"

    def test_get_uncommitted_events_returns_copy(self):
        """Test that get_uncommitted_events returns a copy, not reference"""
        plugin_id = uuid4()
        developer_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)
        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test",
                developer_id=developer_id,
                category="test",
                price=0.0,
            )
        )

        events = aggregate.get_uncommitted_events()
        original_count = len(events)

        # Try to modify the returned list
        events.clear()

        # Original should be unchanged
        assert len(aggregate.get_uncommitted_events()) == original_count


class TestAggregateStateReconstruction:
    """Test aggregate state reconstruction from events"""

    def test_load_from_history_rebuilds_state(self):
        """Test that loading from history rebuilds aggregate state"""
        plugin_id = uuid4()
        developer_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        # Create some events
        events = [
            {
                "event_type": "PluginListed",
                "data": {
                    "plugin_id": str(plugin_id),
                    "plugin_name": "Test Plugin",
                    "developer_id": str(developer_id),
                    "category": "productivity",
                    "price": 9.99,
                    "description": "Test description",
                },
            }
        ]

        # Convert to Event objects (simplified for test)
        from src.shared.events.event import Event, EventMetadata

        event_objects = [
            Event(
                metadata=EventMetadata(
                    event_id=uuid4(), event_type="PluginListed", timestamp=datetime.now(timezone.utc)
                ),
                data=e["data"],
            )
            for e in events
        ]

        # Load from history
        aggregate.load_from_history(event_objects)

        # Verify state was rebuilt
        assert aggregate.status == PluginStatus.LISTED
        assert aggregate.plugin_name == "Test Plugin"
        assert aggregate.category == "productivity"
        assert aggregate.price == 9.99

    def test_version_increments_with_each_event(self):
        """Test that aggregate version increments with each event"""
        plugin_id = uuid4()
        developer_id = uuid4()

        aggregate = MarketplaceAggregate(plugin_id)

        assert aggregate.version == 0

        aggregate.list_plugin(
            ListPluginCommand(
                plugin_id=plugin_id,
                plugin_name="Test",
                developer_id=developer_id,
                category="test",
                price=0.0,
            )
        )

        assert aggregate.version == 1
