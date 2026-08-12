# services/plugin-state-manager/core/license.py
"""
License validation logic
"""

import logging
import os
from typing import Optional

import asyncpg
import httpx
from models.plugin_state import LicenseTier

from config import settings
from shared.models.tiers import TIER_RANK, normalize_tier, tier_rank

logger = logging.getLogger(__name__)


async def validate_tool_access(
    conn: asyncpg.Connection, user_id: str, tool_name: str
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
    async with httpx.AsyncClient(timeout=settings.CATALOG_HTTP_TIMEOUT) as client:
        response = await client.get(
            f"{settings.MARKETPLACE_URL}/v1/marketplace/ai/tools",
            params={"tool_name": tool_name},
        )

        if response.status_code != 200:
            return {
                "allowed": False,
                "tier_required": "community",
                "user_tier": "unknown",
                "reason": f"Tool {tool_name} not found",
            }

        tools_data = response.json()
        tools = tools_data.get("tools", [])

        if not tools:
            return {
                "allowed": False,
                "tier_required": "community",
                "user_tier": "unknown",
                "reason": f"Tool {tool_name} not found",
            }

        tool = tools[0]
        required_tier = tool.get("required_tier", "community")

    # Get user's subscription tier.
    # No user/subscription system exists yet (#47), so every caller is treated as
    # the lowest real tier ("community"). This is FAIL CLOSED: pro/enterprise
    # tools are denied to everyone until a real per-user tier lookup is wired in.
    # `user_id` / `conn` are accepted now for a forward-compatible signature.
    user_tier = "community"

    # Rank comparison via the shared tier vocabulary (#142). normalize_tier maps the
    # legacy "professional" spelling to "pro"; a genuinely unknown required tier now
    # fails CLOSED (deny) instead of the old dict-default of 0, which fail-OPENED a
    # paid tool (unknown tier → required_level 0 → everyone allowed).
    user_level = tier_rank(user_tier)
    try:
        required_tier = normalize_tier(required_tier).value
        required_level = tier_rank(required_tier)
    except ValueError:
        logger.warning(
            "Unknown required_tier %r for tool %s — denying (fail closed)",
            required_tier,
            tool_name,
        )
        required_level = max(TIER_RANK.values()) + 1

    allowed = user_level >= required_level

    if not allowed:
        reason = f"This tool requires {required_tier} tier or higher. Your current tier: {user_tier}"
    else:
        reason = None

    return {
        "allowed": allowed,
        "tier_required": required_tier,
        "user_tier": user_tier,
        "reason": reason,
    }


async def get_plugin_license_tier(
    conn: asyncpg.Connection, plugin_name: str
) -> LicenseTier:
    """Get plugin's required license tier"""
    row = await conn.fetchrow(
        "SELECT license_tier FROM plugin_states WHERE plugin_name = $1", plugin_name
    )

    if row:
        # normalize_tier tolerates a legacy "professional" row → "pro" instead of
        # raising ValueError (which would 500 the request) (#142).
        return normalize_tier(row["license_tier"])

    # Check default plugins
    default_row = await conn.fetchrow(
        "SELECT min_tier FROM default_plugins WHERE plugin_name = $1", plugin_name
    )

    if default_row:
        return normalize_tier(default_row["min_tier"])

    return LicenseTier.COMMUNITY


async def check_plugin_license(
    conn: asyncpg.Connection, plugin_name: str, license_key: Optional[str] = None
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
            "message": "No license key required",
        }

    # For paid plugins, validate license key
    if not license_key:
        return {
            "valid": False,
            "tier": required_tier.value,
            "message": f"License key required for {required_tier.value} tier",
        }

    # Paid-tier plugins require a *validated* license key. A real license /
    # subscription store does not exist yet (#47), so we FAIL CLOSED instead of
    # the old "accept any non-empty key" bypass (which let any string unlock
    # pro/enterprise plugins). No paid plugins ship today, so this is inert in
    # practice — it only removes the bypass. A documented dev override exists for
    # local testing of the paid path.
    if os.getenv("MINDER_ALLOW_UNVALIDATED_LICENSES") == "1":
        logger.warning(
            "MINDER_ALLOW_UNVALIDATED_LICENSES=1 — accepting UNVALIDATED license "
            "key for %s (%s tier). DEV ONLY; never set this in production.",
            plugin_name,
            required_tier.value,
        )
        return {
            "valid": True,
            "tier": required_tier.value,
            "message": "License accepted via dev override (unvalidated)",
        }

    return {
        "valid": False,
        "tier": required_tier.value,
        "message": (
            f"License validation for the {required_tier.value} tier is not yet "
            "implemented; rejecting by default (#47)."
        ),
    }


async def update_plugin_license(
    conn: asyncpg.Connection,
    plugin_name: str,
    license_tier: LicenseTier,
    license_key: Optional[str] = None,
) -> Optional[dict]:
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
        plugin_name,
    )

    return dict(row) if row else None
