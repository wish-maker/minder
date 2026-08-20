# services/marketplace/routes/marketplace.py
import json
import uuid
from datetime import datetime
from typing import Any, List, Optional

import asyncpg
from core.database import get_pool
from core.plugin_repository import PLUGIN_COLUMNS
from core.plugin_repository import get_featured_plugins as _get_featured_plugins_page
from core.plugin_repository import (
    get_plugin_by_id,
    list_plugins_page,
    row_to_plugin_response,
    search_plugins_page,
)
from core.validation import valid_plugin_id
from fastapi import APIRouter, Depends, HTTPException, Query
from models.plugin import (
    PluginCreate,
    PluginListResponse,
    PluginResponse,
    PluginStatus,
    PluginUpdate,
)

from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error

# Fields a PUT /plugins/{id} may change (whitelist → safe to interpolate as column
# names; values always go through bound parameters).
_PLUGIN_UPDATABLE = {
    "name",
    "display_name",
    "description",
    "author",
    "pricing_model",
    "base_tier",
    "status",
    "featured",
    "requires_services",
}

# requires_services is JSONB but asyncpg has no codec registered for it here (no
# create_pool(..., init=...) sets one up), so it round-trips as a raw JSON string --
# json.dumps() going in, json.loads() coming out -- same convention already used for
# manifest/config JSONB columns elsewhere in this codebase (plugin-registry's
# core/database.py).
_JSONB_UPDATABLE = {"requires_services"}


router = APIRouter(prefix="/v1/marketplace", tags=["Marketplace"])


def _resolve_pagination(
    limit: Optional[int], offset: Optional[int], page: int, page_size: int
) -> tuple[int, int]:
    """Resolve effective ``(limit, offset)``.

    ``limit``/``offset`` (the platform-standard vocabulary, #147/C6) win when
    supplied; otherwise fall back to the deprecated ``page``/``page_size``.
    """
    if limit is not None or offset is not None:
        return (limit if limit is not None else 10, offset if offset is not None else 0)
    return page_size, (page - 1) * page_size


def _build_list_response(
    plugins: List[Any], total_count: int, limit: int, offset: int
) -> PluginListResponse:
    """Assemble a PluginListResponse populating both pagination vocabularies."""
    page = (offset // limit) + 1 if limit else 1
    total_pages = (total_count + limit - 1) // limit if limit else 0
    return PluginListResponse(
        plugins=plugins,
        count=len(plugins),
        total=total_count,
        limit=limit,
        offset=offset,
        page=page,
        page_size=limit,
        total_pages=total_pages,
    )


@router.get("/plugins", response_model=PluginListResponse)
async def list_plugins(
    limit: Optional[int] = Query(
        None, ge=1, le=100, description="Page size (canonical)"
    ),
    offset: Optional[int] = Query(None, ge=0, description="Items to skip (canonical)"),
    page: int = Query(
        1, ge=1, deprecated=True, description="Deprecated: use limit/offset"
    ),
    page_size: int = Query(
        10, ge=1, le=100, deprecated=True, description="Deprecated: use limit/offset"
    ),
    category: Optional[str] = None,
    pricing_model: Optional[str] = None,
    status: Optional[str] = "approved",
):
    """
    List all plugins in marketplace

    Args:
        limit: Page size (canonical, platform-standard)
        offset: Items to skip (canonical, platform-standard)
        page: Deprecated — page number (1-indexed); use limit/offset
        page_size: Deprecated — items per page; use limit/offset
        category: Filter by category
        pricing_model: Filter by pricing model
        status: Filter by status (default: approved)
    """
    eff_limit, eff_offset = _resolve_pagination(limit, offset, page, page_size)
    pool = await get_pool()

    plugins, total_count = await list_plugins_page(
        pool, status, category, pricing_model, eff_limit, eff_offset
    )

    return _build_list_response(plugins, total_count, eff_limit, eff_offset)


@router.get("/plugins/search", response_model=PluginListResponse)
async def search_plugins(
    q: str = Query(..., min_length=1),
    limit: Optional[int] = Query(
        None, ge=1, le=100, description="Page size (canonical)"
    ),
    offset: Optional[int] = Query(None, ge=0, description="Items to skip (canonical)"),
    page: int = Query(
        1, ge=1, deprecated=True, description="Deprecated: use limit/offset"
    ),
    page_size: int = Query(
        10, ge=1, le=100, deprecated=True, description="Deprecated: use limit/offset"
    ),
):
    """Search plugins by name or description"""
    pool = await get_pool()
    eff_limit, eff_offset = _resolve_pagination(limit, offset, page, page_size)

    plugins, total_count = await search_plugins_page(pool, q, eff_limit, eff_offset)

    return _build_list_response(plugins, total_count, eff_limit, eff_offset)


@router.post("/plugins", response_model=PluginResponse, status_code=201)
async def create_plugin(
    plugin_data: PluginCreate,
    current_user: dict = Depends(get_current_user_or_service),
):
    """
    Create a new plugin in marketplace.

    Two distinct callers (#402):
    - the plugin registry (internal **service** token) auto-registering a
      first-party module plugin → created `approved` + `origin='first_party'`,
      as before (these bypass human review by design).
    - a **user** JWT (a developer) → created as a `draft` submission
      (`origin='submitted'`, `submitted_by=<sub>`) that must go through the
      review flow (routes/submissions.py) before it can become visible. This
      closes the prior gap where ANY authenticated user could POST a listing
      that was silently auto-approved and publicly visible immediately.
    """
    pool = await get_pool()

    is_service = current_user.get("role") == "service"
    status = "approved" if is_service else PluginStatus.DRAFT.value
    origin = "first_party" if is_service else "submitted"
    submitted_by = None if is_service else current_user.get("sub")

    try:
        async with pool.acquire() as conn:
            # Generate plugin ID
            plugin_id = str(uuid.uuid4())

            # Insert plugin
            row = await conn.fetchrow(
                f"""
                INSERT INTO marketplace_plugins (
                    id, name, display_name, description, author, author_email,
                    repository_url, distribution_type, docker_image,
                    pricing_model, base_tier, status, developer_id, category_id,
                    requires_services, origin, submitted_by, submitted_at,
                    download_count, rating_count, featured, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15::jsonb,
                    $16, $17, $18, 0, 0, FALSE, NOW(), NOW()
                )
                RETURNING {PLUGIN_COLUMNS}
                """,
                plugin_id,
                plugin_data.name,
                plugin_data.display_name,
                plugin_data.description,
                plugin_data.author,
                plugin_data.author_email,
                str(plugin_data.repository_url) if plugin_data.repository_url else None,
                plugin_data.distribution_type.value,
                plugin_data.docker_image,
                plugin_data.pricing_model.value,
                plugin_data.base_tier,
                status,
                plugin_data.developer_id,
                plugin_data.category_id,
                json.dumps(plugin_data.requires_services),
                origin,
                submitted_by,
                # submitted_at: stamped now for a draft submission; null for the
                # service auto-register path.
                None if is_service else datetime.utcnow(),
            )

            return row_to_plugin_response(row)

    except Exception as e:
        raise backend_http_error(e, "Creating plugin")


@router.get("/plugins/featured", response_model=PluginListResponse)
async def get_featured_plugins(limit: int = Query(10, ge=1, le=50)):
    """Get featured plugins"""
    pool = await get_pool()

    plugins = await _get_featured_plugins_page(pool, limit)

    return PluginListResponse(
        plugins=plugins, count=len(plugins), page=1, page_size=limit, total_pages=1
    )


@router.get("/plugins/{plugin_id}", response_model=PluginResponse)
async def get_plugin(plugin_id: str = Depends(valid_plugin_id)):
    """Get plugin by ID"""
    pool = await get_pool()

    plugin = await get_plugin_by_id(pool, plugin_id)

    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    return plugin


@router.put("/plugins/{plugin_id}", response_model=PluginResponse)
async def update_plugin(
    plugin_update: PluginUpdate,
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user_or_service),
):
    """Partially update a plugin's marketplace metadata.

    Only the fields present in the body are changed (the `PluginUpdate` model existed
    but had no route — #147). 404 if the plugin is unknown, 422 if the body is empty.
    """
    # mode="json" serialises the PricingModel/PluginStatus enums to their string values
    # for the SQL params.
    updates = {
        k: v
        for k, v in plugin_update.model_dump(mode="json", exclude_unset=True).items()
        if k in _PLUGIN_UPDATABLE
    }
    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields provided")

    for col in _JSONB_UPDATABLE:
        if col in updates:
            updates[col] = json.dumps(updates[col])

    # Column names come from the _PLUGIN_UPDATABLE whitelist (never user input);
    # values are always bound parameters.
    set_clause = ", ".join(
        f"{col} = ${i}" + ("::jsonb" if col in _JSONB_UPDATABLE else "")
        for i, col in enumerate(updates, start=1)
    )
    params = list(updates.values())
    query = (
        f"UPDATE marketplace_plugins SET {set_clause}, updated_at = NOW() "
        f"WHERE id = ${len(params) + 1} "
        f"RETURNING {PLUGIN_COLUMNS}"
    )

    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            # #402 §6.6: the plugin-registry auto-sync updates first-party
            # listings in place via this endpoint (service token). It must NOT
            # clobber a HUMAN developer submission (`origin='submitted'`) that
            # happens to share a name — a rename/reconcile could otherwise
            # silently overwrite someone's under-review submission. A real admin
            # JWT may still edit any row; only the service principal is fenced.
            if current_user.get("role") == "service":
                existing = await conn.fetchrow(
                    "SELECT origin FROM marketplace_plugins WHERE id = $1",
                    plugin_id,
                )
                if existing is not None and existing["origin"] == "submitted":
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Refusing to overwrite a developer submission "
                            "(origin='submitted') from the service sync path"
                        ),
                    )
            row = await conn.fetchrow(query, *params, plugin_id)
    except asyncpg.UniqueViolationError:
        # #747: a renamed plugin's id-based sync could collide with a
        # DIFFERENT plugin that already has the new name -- a real conflict,
        # not a bad request, and better than a raw 500 (name is UNIQUE NOT
        # NULL on marketplace_plugins).
        raise HTTPException(
            status_code=409,
            detail=f"A plugin named {updates.get('name')!r} already exists",
        )

    if not row:
        raise HTTPException(status_code=404, detail="Plugin not found")

    return row_to_plugin_response(row)
