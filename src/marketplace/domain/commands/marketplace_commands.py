# src/marketplace/domain/commands/marketplace_commands.py

from dataclasses import dataclass
from typing import Optional
from uuid import UUID


@dataclass
class ListPluginCommand:
    """Command to list a plugin in the marketplace"""

    plugin_id: UUID
    plugin_name: str
    developer_id: UUID
    category: str
    price: float
    description: Optional[str] = None


@dataclass
class PurchaseLicenseCommand:
    """Command to purchase a plugin license"""

    license_id: UUID
    plugin_id: UUID
    user_id: UUID
    license_type: str  # TRIAL, STANDARD, PREMIUM
    expiry_days: Optional[int] = None


@dataclass
class DelistPluginCommand:
    """Command to remove a plugin from the marketplace"""

    plugin_id: UUID
    reason: str
    delisted_by: UUID
