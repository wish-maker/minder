# src/marketplace/domain/events/marketplace_events.py

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from src.shared.events.event import DomainEvent


@dataclass
class PluginListed(DomainEvent):
    """Emitted when plugin is listed in marketplace"""

    plugin_id: UUID = field(default_factory=uuid4)
    plugin_name: str = ""
    developer_id: UUID = field(default_factory=uuid4)
    category: str = ""
    price: float = 0.0
    description: Optional[str] = None
    listing_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LicensePurchased(DomainEvent):
    """Emitted when user purchases plugin license"""

    license_id: UUID = field(default_factory=uuid4)
    plugin_id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    license_type: str = ""  # TRIAL, STANDARD, PREMIUM
    expiry_date: Optional[datetime] = None
    purchase_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class LicenseExpired(DomainEvent):
    """Emitted when license expires"""

    license_id: UUID = field(default_factory=uuid4)
    plugin_id: UUID = field(default_factory=uuid4)
    user_id: UUID = field(default_factory=uuid4)
    expiry_date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class PluginDelisted(DomainEvent):
    """Emitted when plugin is removed from marketplace"""

    plugin_id: UUID = field(default_factory=uuid4)
    reason: str = ""
    delisted_by: UUID = field(default_factory=uuid4)
    delisted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
