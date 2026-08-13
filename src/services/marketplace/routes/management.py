# services/marketplace/routes/management.py
from core.database import get_pool
from core.validation import valid_plugin_id
from fastapi import APIRouter, Depends, HTTPException, Query
from models.installation import InstallationResponse

from shared.auth.jwt_middleware import get_current_user

router = APIRouter(prefix="/v1/marketplace/plugins", tags=["Plugin Management"])


@router.post("/{plugin_id}/install", response_model=InstallationResponse)
async def install_plugin(
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user),
):
    """Install a plugin for the authenticated user.

    The user identity comes from the JWT (`sub`) — it used to be a redundant `user_id`
    in the request body/query that duplicated the authenticated principal (#147/C7).

    plugin_id is str()-cast before InstallationResponse construction: asyncpg returns
    UUID columns as uuid.UUID objects, and InstallationResponse.plugin_id is a `str`
    field -- pydantic v2 does not coerce UUID -> str, so this 500'd on response
    serialization for every install until fixed (#402, found live on hantal).
    """
    user_id = current_user["sub"]
    pool = await get_pool()

    # Check if plugin exists
    async with pool.acquire() as conn:
        plugin = await conn.fetchrow(
            "SELECT * FROM marketplace_plugins WHERE id = $1", plugin_id
        )

        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")

        # Check if already installed
        existing = await conn.fetchrow(
            """
            SELECT * FROM marketplace_installations
            WHERE user_id = $1 AND plugin_id = $2
            """,
            user_id,
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
                plugin_id=str(existing["plugin_id"]),
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
            user_id,
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
            plugin_id=str(row["plugin_id"]),
            version=row["version"],
            status=row["status"],
            enabled=row["enabled"],
            config_json=row["config_json"],
            installed_at=row["installed_at"],
            last_updated_at=row["last_updated_at"],
        )


@router.delete("/{plugin_id}/uninstall")
async def uninstall_plugin(
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user),
):
    """Uninstall the authenticated user's plugin (identity from JWT, #147/C7)."""
    user_id = current_user["sub"]
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
async def enable_plugin(
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user),
):
    """Enable the authenticated user's plugin (identity from JWT, #147/C7)."""
    user_id = current_user["sub"]
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
async def disable_plugin(
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user),
):
    """Disable the authenticated user's plugin (identity from JWT, #147/C7)."""
    user_id = current_user["sub"]
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
async def get_plugin_installations(
    plugin_id: str = Depends(valid_plugin_id),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Get a plugin's installations (admin endpoint), paginated (#147/C6)."""
    pool = await get_pool()

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM marketplace_installations WHERE plugin_id = $1",
            plugin_id,
        )
        rows = await conn.fetch(
            """
            SELECT * FROM marketplace_installations
            WHERE plugin_id = $1
            ORDER BY installed_at DESC
            LIMIT $2 OFFSET $3
            """,
            plugin_id,
            limit,
            offset,
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

        return {
            "installations": installations,
            "count": len(installations),
            "total": total,
            "limit": limit,
            "offset": offset,
        }
