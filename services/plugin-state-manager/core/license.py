# services/plugin-state-manager/core/license.py
"""
License validation logic
"""

import logging
from datetime import datetime
from typing import Optional

import asyncpg
import httpx

from models.plugin_state import LicenseTier
from models.tool_execution import ToolSchema

logger = logging.getLogger(__name__)


async def validate_tool_access(
    conn: asyncpg.Connection,
    user_id: str,
    tool_name: str
) -> dict:
    """
    Validate if user has access to a tool based on license tier

    Args:
        conn: Database connection
        user_id: User ID
        tool_name: Tool name to validate

    Returns:
        Validation result with allowed flag and reason
    """
    # Get tool details from marketplace
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "http://minder-marketplace:8002/v1/marketplace/ai/tools",
            params={"tool_name": tool_name}
        )

        if response.status_code != 200:
            return {
                "allowed": False,
                "tier_required": "community",
                "user_tier": "unknown",
                "reason": f"Tool {tool_name} not found"
            }

        tools_data = response.json()
        tools = tools_data.get("tools", [])

        if not tools:
            return {
                "allowed": False,
                "tier_required": "community",
                "user_tier": "unknown",
                "reason": f"Tool {tool_name} not found"
            }

        tool = tools[0]
        required_tier = tool.get("required_tier", "community")

    # Get user's subscription tier
    # For now, default to community tier (TODO: integrate with actual user system)
    user_tier = "community"

    # Define tier hierarchy
    tier_hierarchy = {
        "free": 0,
        "community": 1,
        "pro": 2,
        "enterprise": 3
    }

    user_level = tier_hierarchy.get(user_tier, 0)
    required_level = tier_hierarchy.get(required_tier, 0)

    allowed = user_level >= required_level

    if not allowed:
        reason = f"This tool requires {required_tier} tier or higher. Your current tier: {user_tier}"
    else:
        reason = None

    return {
        "allowed": allowed,
        "tier_required": required_tier,
        "user_tier": user_tier,
        "reason": reason
    }


async def get_plugin_license_tier(
    conn: asyncpg.Connection,
    plugin_name: str
) -> LicenseTier:
    """Get plugin's required license tier"""
    row = await conn.fetchrow(
        "SELECT license_tier FROM plugin_states WHERE plugin_name = $1",
        plugin_name
    )

    if row:
        return LicenseTier(row["license_tier"])

    # Check default plugins
    default_row = await conn.fetchrow(
        "SELECT min_tier FROM default_plugins WHERE plugin_name = $1",
        plugin_name
    )

    if default_row:
        return LicenseTier(default_row["min_tier"])

    return LicenseTier.COMMUNITY


async def check_plugin_license(
    conn: asyncpg.Connection,
    plugin_name: str,
    license_key: Optional[str] = None
) -> dict:
    """
    Check if plugin license is valid

    Args:
        conn: Database connection
        plugin_name: Plugin name
        license_key: Optional license key to validate

    Returns:
        License validation result
    """
    # Get plugin's required tier
    required_tier = await get_plugin_license_tier(conn, plugin_name)

    # For free/community plugins, no license key needed
    if required_tier in [LicenseTier.FREE, LicenseTier.COMMUNITY]:
        return {
            "valid": True,
            "tier": required_tier.value,
            "message": "No license key required"
        }

    # For paid plugins, validate license key
    if not license_key:
        return {
            "valid": False,
            "tier": required_tier.value,
            "message": f"License key required for {required_tier.value} tier"
        }

    # TODO: Implement actual license key validation
    # For now, accept any non-empty key
    return {
        "valid": True,
        "tier": required_tier.value,
        "message": "License key validated"
    }


async def update_plugin_license(
    conn: asyncpg.Connection,
    plugin_name: str,
    license_tier: LicenseTier,
    license_key: Optional[str] = None
) -> dict:
    """
    Update plugin's license information

    Args:
        conn: Database connection
        plugin_name: Plugin name
        license_tier: License tier
        license_key: Optional license key

    Returns:
        Updated plugin state
    """
    row = await conn.fetchrow(
        """
        UPDATE plugin_states
        SET license_tier = $1, license_key = $2, updated_at = NOW()
        WHERE plugin_name = $3
        RETURNING *
        """,
        license_tier.value,
        license_key,
        plugin_name
    )

    return dict(row) if row else None
