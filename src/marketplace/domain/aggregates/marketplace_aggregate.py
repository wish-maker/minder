# src/marketplace/domain/aggregates/marketplace_aggregate.py

from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID, uuid4

from src.marketplace.domain.commands.marketplace_commands import (
    DelistPluginCommand,
    ListPluginCommand,
    PurchaseLicenseCommand,
)
from src.shared.domain.aggregate import Aggregate
from src.shared.events.event import Event, EventMetadata


class PluginStatus(Enum):
    """Plugin listing status"""

    LISTED = "listed"
    DELISTED = "delisted"


class MarketplaceAggregate(Aggregate):
    """
    Aggregate for Marketplace domain.

    Manages plugin marketplace lifecycle including listing, delisting,
    and license purchases. All state changes are recorded as events
    in the Event Store.

    Attributes:
        id: Aggregate unique identifier
        plugin_id: Plugin identifier
        plugin_name: Plugin display name
        developer_id: Plugin developer identifier
        category: Plugin category
        price: Plugin price
        description: Plugin description
        status: Current listing status (listed, delisted)
        version: Aggregate version (optimistic locking counter)
    """

    def __init__(self, id: UUID):
        """
        Initialize marketplace aggregate.

        Args:
            id: Unique identifier for this marketplace aggregate
        """
        super().__init__(id)
        self.plugin_id: UUID = None
        self.plugin_name: str = None
        self.developer_id: UUID = None
        self.category: str = None
        self.price: float = None
        self.description: str = None
        self.status: PluginStatus = PluginStatus.DELISTED

    def list_plugin(self, command: ListPluginCommand) -> None:
        """
        List a plugin in the marketplace.

        Args:
            command: ListPluginCommand with plugin details

        Raises:
            ValueError: If plugin already listed
        """
        if self.status == PluginStatus.LISTED:
            raise ValueError("Plugin already listed")

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="PluginListed",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "plugin_id": str(command.plugin_id),
                "plugin_name": command.plugin_name,
                "developer_id": str(command.developer_id),
                "category": command.category,
                "price": command.price,
                "description": command.description,
                "listing_date": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def delist_plugin(self, command: DelistPluginCommand) -> None:
        """
        Remove a plugin from the marketplace.

        Args:
            command: DelistPluginCommand with plugin_id, reason, and delisted_by

        Raises:
            ValueError: If plugin not listed
        """
        if self.status != PluginStatus.LISTED:
            raise ValueError("Plugin not listed")

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="PluginDelisted",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "plugin_id": str(self.plugin_id),
                "reason": command.reason,
                "delisted_by": str(command.delisted_by),
                "delisted_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def purchase_license(self, command: PurchaseLicenseCommand) -> None:
        """
        Purchase a license for a plugin.

        Args:
            command: PurchaseLicenseCommand with license details

        Raises:
            ValueError: If plugin not listed
        """
        if self.status != PluginStatus.LISTED:
            raise ValueError("Cannot purchase license for unlisted plugin")

        event = Event(
            metadata=EventMetadata(
                event_id=self._next_event_id(),
                event_type="LicensePurchased",
                timestamp=datetime.now(timezone.utc),
            ),
            data={
                "license_id": str(command.license_id),
                "plugin_id": str(command.plugin_id),
                "user_id": str(command.user_id),
                "license_type": command.license_type,
                "expiry_date": (
                    self._calculate_expiry_date(command.expiry_days).isoformat() if command.expiry_days else None
                ),
                "purchase_date": datetime.now(timezone.utc).isoformat(),
            },
        )

        self._apply_event(event, version=self.version + 1)

    def _apply(self, event: Event) -> None:
        """
        Apply event to aggregate state.

        Args:
            event: Event to apply
        """
        if event.event_type == "PluginListed":
            self._apply_plugin_listed(event)
        elif event.event_type == "PluginDelisted":
            self._apply_plugin_delisted(event)
        elif event.event_type == "LicensePurchased":
            self._apply_license_purchased(event)

    def _apply_plugin_listed(self, event: Event) -> None:
        """Apply PluginListed event to aggregate state"""
        self.plugin_id = UUID(event.data["plugin_id"])
        self.plugin_name = event.data["plugin_name"]
        self.developer_id = UUID(event.data["developer_id"])
        self.category = event.data["category"]
        self.price = event.data["price"]
        self.description = event.data.get("description")
        self.status = PluginStatus.LISTED

    def _apply_plugin_delisted(self, event: Event) -> None:
        """Apply PluginDelisted event to aggregate state"""
        self.status = PluginStatus.DELISTED

    def _apply_license_purchased(self, event: Event) -> None:
        """Apply LicensePurchased event to aggregate state"""
        # License purchases don't change the plugin state
        # but are recorded for audit and billing purposes
        pass

    def _next_event_id(self) -> UUID:
        """Generate next event ID for this aggregate"""
        return uuid4()

    def _calculate_expiry_date(self, expiry_days: int) -> datetime:
        """Calculate license expiry date"""
        return datetime.now(timezone.utc) + timedelta(days=expiry_days)
