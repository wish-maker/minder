# services/marketplace/routes/management.py
from core.database import get_pool
from core.neo4j_client import Neo4jClient, get_neo4j_client
from core.validation import valid_plugin_id
from fastapi import APIRouter, Depends, HTTPException, Query
from models.installation import InstallationResponse

from config import settings
from shared.auth.jwt_middleware import get_current_user, require_role

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

        # Cap installs per user (MAX_PLUGINS_PER_USER) -- was defined in config but
        # never enforced anywhere, so a single user could install every plugin in
        # the catalog with no limit. Only counts toward a genuinely NEW
        # installation (this branch); re-enabling an already-installed plugin
        # (the `existing` branch above) doesn't add a new row.
        install_count = await conn.fetchval(
            """
            SELECT COUNT(*) FROM marketplace_installations
            WHERE user_id = $1 AND status = 'installed'
            """,
            user_id,
        )
        if install_count >= settings.MAX_PLUGINS_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Plugin install limit reached ({settings.MAX_PLUGINS_PER_USER} "
                    "per user) -- uninstall an existing plugin before installing another."
                ),
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
    neo4j: Neo4jClient = Depends(get_neo4j_client),
):
    """Enable the authenticated user's plugin (identity from JWT, #147/C7).

    #748: the plugin dependency graph (Neo4j DEPENDS_ON) used to be purely
    informational -- a real runtime dependency (e.g. "network" reads
    plugin_instances["telegraf"] directly) could be silently unmet with zero
    warning. This resolves the FULL transitive dependency chain and makes
    sure every one of them is enabled for this user first. A dependency this
    user never installed at all can't be silently auto-installed on their
    behalf (that would bypass their own install choice) -- rejected with a
    clear error naming it instead.
    """
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

        auto_enabled_dependencies = await _ensure_dependencies_enabled(
            conn, user_id, plugin_id, neo4j
        )

        # Enable
        await conn.execute(
            """
            UPDATE marketplace_installations
            SET enabled = TRUE, last_updated_at = NOW()
            WHERE id = $1
            """,
            existing["id"],
        )

        return {
            "status": "enabled",
            "plugin_id": plugin_id,
            "auto_enabled_dependencies": auto_enabled_dependencies,
        }


async def _ensure_dependencies_enabled(
    conn, user_id: str, plugin_id: str, neo4j: Neo4jClient
) -> list:
    """Enable every transitive DEPENDS_ON dependency of `plugin_id` that this
    user has installed but not yet enabled (#748). Returns the display names
    of whichever dependencies actually got flipped from disabled to enabled.

    Raises HTTPException(409) if any dependency has no installation row at
    all for this user -- auto-INSTALLING on their behalf would bypass their
    own choice, so this only ever auto-*enables* an already-installed row.
    """
    dependencies = await neo4j.get_dependency_chain(plugin_id)
    if not dependencies:
        return []

    dep_ids = [d["plugin_id"] for d in dependencies]
    dep_rows = await conn.fetch(
        """
        SELECT plugin_id, enabled FROM marketplace_installations
        WHERE user_id = $1 AND plugin_id = ANY($2::uuid[])
        """,
        user_id,
        dep_ids,
    )
    installed_by_id = {str(r["plugin_id"]): r for r in dep_rows}

    missing = [d for d in dependencies if d["plugin_id"] not in installed_by_id]
    if missing:
        names = ", ".join(d.get("name") or d["plugin_id"] for d in missing)
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot enable: required dependency not installed: {names}. "
                "Install it first, then try enabling again."
            ),
        )

    auto_enabled = []
    for dep in dependencies:
        row = installed_by_id[dep["plugin_id"]]
        if not row["enabled"]:
            await conn.execute(
                """
                UPDATE marketplace_installations
                SET enabled = TRUE, last_updated_at = NOW()
                WHERE user_id = $1 AND plugin_id = $2
                """,
                user_id,
                dep["plugin_id"],
            )
            auto_enabled.append(dep.get("name") or dep["plugin_id"])
    return auto_enabled


@router.post("/{plugin_id}/disable")
async def disable_plugin(
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user),
    neo4j: Neo4jClient = Depends(get_neo4j_client),
):
    """Disable the authenticated user's plugin (identity from JWT, #147/C7).

    #748: rejected with 409 if another of this user's plugins is enabled and
    directly depends on this one (Neo4j DEPENDS_ON graph). enable_plugin's own
    transitive auto-enable keeps the invariant "an enabled plugin's every
    dependency is enabled" true going forward, so a direct (one-hop) check
    here is sufficient to catch a violation regardless of how deep the real
    dependency chain goes -- if some plugin two hops up were enabled, its own
    direct dependency (one hop up from this one) would already have been
    auto-enabled alongside it, and IT is what this check catches.
    """
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

        dependents = await neo4j.get_dependent_plugins(plugin_id)
        if dependents:
            dependent_ids = [d["plugin_id"] for d in dependents]
            blocking_rows = await conn.fetch(
                """
                SELECT plugin_id FROM marketplace_installations
                WHERE user_id = $1 AND plugin_id = ANY($2::uuid[]) AND enabled = TRUE
                """,
                user_id,
                dependent_ids,
            )
            blocking_ids = {str(r["plugin_id"]) for r in blocking_rows}
            blocking_names = [
                d.get("name") or d["plugin_id"]
                for d in dependents
                if d["plugin_id"] in blocking_ids
            ]
            if blocking_names:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Cannot disable: still-enabled plugin(s) depend on this "
                        "one: " + ", ".join(blocking_names)
                    ),
                )

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
    current_user: dict = Depends(require_role("admin")),
):
    """Get a plugin's installations, paginated (#147/C6).

    Admin-only (#474) -- this had NO authentication at all before: any caller
    could list every user_id that installed a given plugin. The docstring
    always called it "admin endpoint" but nothing enforced that.
    """
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
