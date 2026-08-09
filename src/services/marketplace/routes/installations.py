# services/marketplace/routes/installations.py
from core.database import get_pool
from fastapi import APIRouter, Depends
from models.installation import InstalledPluginSummary, MyInstallationsResponse

from shared.auth.jwt_middleware import get_current_user

# Disjoint prefix, NOT nested under /v1/marketplace/plugins/... -- that router
# already has GET /plugins/{plugin_id} registered first (marketplace.py), and
# Starlette matches routes in registration order, so a literal path segment
# here would be swallowed by that {plugin_id} pattern (the same reason
# /plugins/search and /plugins/featured had to be declared before
# /plugins/{plugin_id} in marketplace.py).
router = APIRouter(prefix="/v1/marketplace/installations", tags=["Plugin Management"])


@router.get("/me", response_model=MyInstallationsResponse)
async def get_my_installations(current_user: dict = Depends(get_current_user)):
    """List the authenticated user's currently-installed plugins, across all
    plugins, with plugin metadata inlined so the client needs no per-plugin
    follow-up fetch just to show a name/description (#402)."""
    user_id = current_user["sub"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT mi.id AS installation_id, mi.plugin_id, mi.version, mi.status,
                   mi.enabled, mi.installed_at, mi.last_updated_at,
                   p.name, p.display_name, p.description, p.current_version,
                   p.pricing_model, p.base_tier, p.category_id, p.author
            FROM marketplace_installations mi
            JOIN marketplace_plugins p ON p.id = mi.plugin_id
            WHERE mi.user_id = $1 AND mi.status = 'installed'
            ORDER BY mi.installed_at DESC
            """,
            user_id,
        )
    # asyncpg returns UUID columns as uuid.UUID objects, not str -- pydantic v2
    # does not coerce those into a `str` field (confirmed: raises string_type),
    # so installation_id/plugin_id need an explicit str() cast here.
    installations = [
        InstalledPluginSummary(
            **{
                **dict(row),
                "installation_id": str(row["installation_id"]),
                "plugin_id": str(row["plugin_id"]),
            }
        )
        for row in rows
    ]
    return MyInstallationsResponse(
        installations=installations, count=len(installations)
    )
