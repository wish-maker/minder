# services/marketplace/routes/management.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.marketplace.core.database import get_pool
from services.marketplace.models.installation import InstallationCreate, InstallationResponse

router = APIRouter(prefix="/v1/marketplace/plugins", tags=["Plugin Management"])


class InstallRequest(BaseModel):
    """Request model for plugin installation"""

    user_id: str


@router.post("/{plugin_id}/install", response_model=InstallationResponse)
async def install_plugin(plugin_id: str, request: InstallRequest):
    """
    Install a plugin for a user

    Args:
        plugin_id: Plugin ID
        request: Installation request with user_id
    """
    pool = await get_pool()

    # Check if plugin exists
    async with pool.acquire() as conn:
        plugin = await conn.fetchrow("SELECT * FROM marketplace_plugins WHERE id = $1", plugin_id)

        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")

        # Check if already installed
        existing = await conn.fetchrow(
            """
            SELECT * FROM marketplace_installations
            WHERE user_id = $1 AND plugin_id = $2
            """,
            request.user_id,
            plugin_id,
        )

        if existing:
            # Update if exists
            await conn.execute(
                """
                UPDATE marketplace_installations
                SET status = 'installed', enabled = TRUE, last_updated_at = NOW()
                WHERE id = $1
                """,
                existing["id"],
            )

            return InstallationResponse(
                id=str(existing["id"]),
                user_id=existing["user_id"],
                plugin_id=existing["plugin_id"],
                version=existing["version"],
                status="installed",
                enabled=True,
                config_json=existing["config_json"],
                installed_at=existing["installed_at"],
                last_updated_at=existing["last_updated_at"],
            )

        # Create new installation
        row = await conn.fetchrow(
            """
            INSERT INTO marketplace_installations (user_id, plugin_id, status, enabled)
            VALUES ($1, $2, 'installed', TRUE)
            RETURNING id, user_id, plugin_id, version, status, enabled, config_json, installed_at, last_updated_at
            """,
            request.user_id,
            plugin_id,
        )

        # Increment download count
        await conn.execute(
            "UPDATE marketplace_plugins SET download_count = download_count + 1 WHERE id = $1",
            plugin_id,
        )

        return InstallationResponse(
            id=str(row["id"]),
            user_id=row["user_id"],
            plugin_id=row["plugin_id"],
            version=row["version"],
            status=row["status"],
            enabled=row["enabled"],
            config_json=row["config_json"],
            installed_at=row["installed_at"],
            last_updated_at=row["last_updated_at"],
        )


@router.delete("/{plugin_id}/uninstall")
async def uninstall_plugin(plugin_id: str, user_id: str = Query(...)):
    """Uninstall a plugin for a user"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Check if installed
        existing = await conn.fetchrow(
            """
            SELECT * FROM marketplace_installations
            WHERE user_id = $1 AND plugin_id = $2
            """,
            user_id,
            plugin_id,
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Plugin not installed")

        # Update status
        await conn.execute(
            """
            UPDATE marketplace_installations
            SET status = 'uninstalled', enabled = FALSE, last_updated_at = NOW()
            WHERE id = $1
            """,
            existing["id"],
        )

        return {"status": "uninstalled", "plugin_id": plugin_id}


@router.post("/{plugin_id}/enable")
async def enable_plugin(plugin_id: str, user_id: str = Query(...)):
    """Enable a plugin for a user"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Check if installed
        existing = await conn.fetchrow(
            """
            SELECT * FROM marketplace_installations
            WHERE user_id = $1 AND plugin_id = $2
            """,
            user_id,
            plugin_id,
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Plugin not installed")

        # Enable
        await conn.execute(
            """
            UPDATE marketplace_installations
            SET enabled = TRUE, last_updated_at = NOW()
            WHERE id = $1
            """,
            existing["id"],
        )

        return {"status": "enabled", "plugin_id": plugin_id}


@router.post("/{plugin_id}/disable")
async def disable_plugin(plugin_id: str, user_id: str = Query(...)):
    """Disable a plugin for a user"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Check if installed
        existing = await conn.fetchrow(
            """
            SELECT * FROM marketplace_installations
            WHERE user_id = $1 AND plugin_id = $2
            """,
            user_id,
            plugin_id,
        )

        if not existing:
            raise HTTPException(status_code=404, detail="Plugin not installed")

        # Disable
        await conn.execute(
            """
            UPDATE marketplace_installations
            SET enabled = FALSE, last_updated_at = NOW()
            WHERE id = $1
            """,
            existing["id"],
        )

        return {"status": "disabled", "plugin_id": plugin_id}


@router.get("/{plugin_id}/installations")
async def get_plugin_installations(plugin_id: str):
    """Get all installations for a plugin (admin endpoint)"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM marketplace_installations
            WHERE plugin_id = $1
            ORDER BY installed_at DESC
            """,
            plugin_id,
        )

        installations = [
            {
                "id": str(row["id"]),
                "user_id": row["user_id"],
                "plugin_id": row["plugin_id"],
                "version": row["version"],
                "status": row["status"],
                "enabled": row["enabled"],
                "installed_at": row["installed_at"].isoformat(),
            }
            for row in rows
        ]

        return {"installations": installations, "count": len(installations)}
