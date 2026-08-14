# services/marketplace/core/licensing.py
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import asyncpg
from core.database import get_pool
from core.security import LicenseGenerator

license_generator = LicenseGenerator()


async def create_license(
    user_id: str, plugin_id: str, tier: str, valid_until: Optional[datetime] = None
) -> Dict:
    """
    Create a new license for a user and plugin

    Returns:
        Dict with license details
    """
    pool = await get_pool()

    # Generate license key
    license_key = license_generator.generate_license_key(
        user_id=user_id, plugin_id=plugin_id, tier=tier
    )

    # Set default validity (1 year) if not specified. `valid_until` is a naive
    # TIMESTAMP column, so store naive-UTC (asyncpg rejects tz-aware values for a
    # `timestamp` column) — fixes the old naive-LOCAL value while keeping the
    # expiry comparison below naive↔naive.
    if valid_until is None:
        valid_until = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(
            days=365
        )

    # Check-then-write, so each attempt must run in its own transaction: without
    # one, two concurrent activate calls for the same user+plugin (a retrying
    # client, a double-click) could each pass the "no active license" SELECT
    # before either commits its INSERT. The partial unique index on
    # (user_id, plugin_id) WHERE active (schema.sql) is what actually closes the
    # race -- the loser's INSERT raises UniqueViolationError, caught below, and
    # the retry takes the UPDATE branch against the winner's now-visible row.
    for attempt in range(2):
        try:
            async with pool.acquire() as conn:
                async with conn.transaction():
                    existing = await conn.fetchrow(
                        """
                        SELECT * FROM marketplace_licenses
                        WHERE user_id = $1 AND plugin_id = $2 AND active = TRUE
                        """,
                        user_id,
                        plugin_id,
                    )

                    if existing:
                        await conn.execute(
                            """
                            UPDATE marketplace_licenses
                            SET tier = $3, license_key = $4, valid_until = $5, updated_at = NOW()
                            WHERE id = $6
                            """,
                            tier,
                            license_key,
                            valid_until,
                            existing["id"],
                        )

                        return {
                            "id": str(existing["id"]),
                            "user_id": existing["user_id"],
                            "plugin_id": existing["plugin_id"],
                            "tier": tier,
                            "license_key": license_key,
                            "valid_from": existing["valid_from"],
                            "valid_until": valid_until,
                            "active": True,
                        }

                    row = await conn.fetchrow(
                        """
                        INSERT INTO marketplace_licenses (
                            user_id, plugin_id, tier, license_key, valid_until, active
                        )
                        VALUES ($1, $2, $3, $4, $5, TRUE)
                        RETURNING id, user_id, plugin_id, tier, license_key, valid_from, valid_until, created_at
                        """,
                        user_id,
                        plugin_id,
                        tier,
                        license_key,
                        valid_until,
                    )

                    return {
                        "id": str(row["id"]),
                        "user_id": row["user_id"],
                        "plugin_id": row["plugin_id"],
                        "tier": row["tier"],
                        "license_key": row["license_key"],
                        "valid_from": row["valid_from"],
                        "valid_until": row["valid_until"],
                        "active": True,
                    }
        except asyncpg.UniqueViolationError:
            if attempt == 1:
                raise
            continue

    raise AssertionError("unreachable")  # loop always returns or raises


async def validate_license(license_key: str, plugin_id: str) -> Dict:
    """
    Validate a license key

    Returns:
        Dict with validation result
    """
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Look up license
        row = await conn.fetchrow(
            """
            SELECT * FROM marketplace_licenses
            WHERE license_key = $1 AND plugin_id = $2 AND active = TRUE
            """,
            license_key,
            plugin_id,
        )

        if not row:
            return {"valid": False, "reason": "License not found or inactive"}

        # Check expiration. row["valid_until"] is naive (naive TIMESTAMP column),
        # so compare against naive-UTC — a tz-aware now() would raise "can't compare
        # offset-naive and offset-aware datetimes".
        if row["valid_until"] and row["valid_until"] < datetime.now(
            timezone.utc
        ).replace(tzinfo=None):
            return {
                "valid": False,
                "reason": "License expired",
                "valid_until": row["valid_until"].isoformat(),
            }

        # Update usage
        await conn.execute(
            """
            UPDATE marketplace_licenses
            SET usage_count = usage_count + 1, last_used_at = NOW()
            WHERE id = $1
            """,
            row["id"],
        )

        return {
            "valid": True,
            "user_id": row["user_id"],
            "plugin_id": row["plugin_id"],
            "tier": row["tier"],
            "valid_until": (
                row["valid_until"].isoformat() if row["valid_until"] else None
            ),
            "usage_count": row["usage_count"] + 1,
        }


async def get_user_licenses(user_id: str) -> list:
    """Get all licenses for a user"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
                l.id, l.user_id, l.plugin_id, l.tier, l.license_key,
                l.valid_from, l.valid_until, l.active, l.usage_count, l.last_used_at,
                p.name as plugin_name, p.display_name as plugin_display_name
            FROM marketplace_licenses l
            JOIN marketplace_plugins p ON l.plugin_id = p.id
            WHERE l.user_id = $1
            ORDER BY l.created_at DESC
            """,
            user_id,
        )

        licenses = []
        for row in rows:
            licenses.append(
                {
                    "id": str(row["id"]),
                    "user_id": row["user_id"],
                    "plugin_id": row["plugin_id"],
                    "plugin_name": row["plugin_name"],
                    "plugin_display_name": row["plugin_display_name"],
                    "tier": row["tier"],
                    "license_key": row["license_key"],
                    "valid_from": row["valid_from"].isoformat(),
                    "valid_until": (
                        row["valid_until"].isoformat() if row["valid_until"] else None
                    ),
                    "active": row["active"],
                    "usage_count": row["usage_count"],
                    "last_used_at": (
                        row["last_used_at"].isoformat() if row["last_used_at"] else None
                    ),
                }
            )

        return licenses
