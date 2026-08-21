# services/marketplace/routes/marketplace.py
import json
import uuid
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

from shared.auth.jwt_middleware import (
    get_current_user_optional,
    get_current_user_or_service,
)
from shared.errors import backend_http_error

# Statuses visible to an unauthenticated/non-privileged caller: the
# publicly-approved catalog, plus the legacy pre-#402 auto-approved value
# ("pending") kept for back-compat. draft/submitted/in_review/rejected are a
# submission's own developer's business (see routes/submissions.py's
# `/mine` and admin-only review queue) and must never be readable by anyone
# else — otherwise the #402 review gate is trivially bypassed by just asking
# for the unapproved status directly.
_PUBLIC_STATUSES = {"approved", "pending"}

# Fields a PUT /plugins/{id} may change (whitelist → safe to interpolate as column
# names; values always go through bound parameters).
#
# `status` is deliberately NOT here (#939): every legal status move has a
# dedicated endpoint under /v1/marketplace/submissions/* that validates the
# transition against the state machine and writes an audit row. Letting PUT set
# `status` directly (an admin fell through to the raw UPDATE) bypassed BOTH —
# permitting illegal moves (draft→approved, archived→approved) with no audit
# trail. The registry auto-sync's PUT never sends `status` either, so nothing
# legitimate relies on it being updatable here.
_PLUGIN_UPDATABLE = {
    "name",
    "display_name",
    "description",
    "author",
    "pricing_model",
    "base_tier",
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
    current_user: Optional[dict] = Depends(get_current_user_optional),
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
        status: Filter by status (default: approved). Non-admin/service callers
            are always clamped to the public catalog regardless of what they
            pass here — see submissions.py for a developer's own submissions.
    """
    is_privileged = current_user is not None and current_user.get("role") in (
        "admin",
        "service",
    )
    if not is_privileged and status not in _PUBLIC_STATUSES:
        status = "approved"
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
                # submitted_at reflects the actual submit action (stamped by
                # routes/submissions.py's transition to SUBMITTED), not draft
                # creation -- null here for both the service auto-register
                # path and a fresh draft that hasn't been submitted yet.
                None,
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
async def get_plugin(
    plugin_id: str = Depends(valid_plugin_id),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """Get plugin by ID.

    A non-public status (draft/submitted/in_review/rejected/archived) is only
    visible to an admin/service caller or the submission's own developer —
    otherwise this is the same unauthenticated-leak class of bug as the
    `status` query param on the list endpoint above (#402 follow-up): the
    id itself isn't secret (it's returned from the create/submit responses),
    so hiding it from listings alone isn't enough.
    """
    pool = await get_pool()

    plugin = await get_plugin_by_id(pool, plugin_id)

    if not plugin:
        raise HTTPException(status_code=404, detail="Plugin not found")

    if plugin.status not in _PUBLIC_STATUSES:
        is_privileged = current_user is not None and current_user.get("role") in (
            "admin",
            "service",
        )
        is_owner = (
            current_user is not None and current_user.get("sub") == plugin.submitted_by
        )
        if not (is_privileged or is_owner):
            raise HTTPException(status_code=404, detail="Plugin not found")

    return plugin


# Fields a plugin's own developer may change on their own draft/rejected
# submission. Deliberately excludes `featured` — that's admin-only curation and
# must never be settable by the submission's own author. (`status` is already
# not in _PLUGIN_UPDATABLE at all, #939 — no PUT caller may set it; status moves
# go through the state machine in routes/submissions.py.)
_OWNER_UPDATABLE = _PLUGIN_UPDATABLE - {"featured"}


@router.put("/plugins/{plugin_id}", response_model=PluginResponse)
async def update_plugin(
    plugin_update: PluginUpdate,
    plugin_id: str = Depends(valid_plugin_id),
    current_user: dict = Depends(get_current_user_or_service),
):
    """Partially update a plugin's marketplace metadata.

    Only the fields present in the body are changed (the `PluginUpdate` model existed
    but had no route — #147). 404 if the plugin is unknown, 422 if the body is empty.

    `status` is not updatable via PUT by anyone (#939) — it moves only through
    the review state machine at /v1/marketplace/submissions/*.

    Non-admin/non-service callers (a submission's own developer) may only edit
    their own `draft`/`rejected` submission, and never `featured` — otherwise a
    developer could feature their own listing or edit anyone else's, bypassing
    the review workflow (#402 follow-up).
    """
    # mode="json" serialises the PricingModel/PluginStatus enums to their string values
    # for the SQL params.
    raw_updates = plugin_update.model_dump(mode="json", exclude_unset=True)
    # #939: `status` is not updatable via PUT for anyone (not even admin) —
    # reject it explicitly (rather than silently dropping it) so the caller is
    # pointed at the state machine instead of believing the change took. This
    # runs before the ownership check on purpose: it's a generic API constraint
    # that reveals nothing about a specific plugin.
    if "status" in raw_updates:
        raise HTTPException(
            status_code=422,
            detail=(
                "status is not updatable via PUT — move it through the review "
                "workflow at /v1/marketplace/submissions/*"
            ),
        )
    updates = {k: v for k, v in raw_updates.items() if k in _PLUGIN_UPDATABLE}
    if not updates:
        raise HTTPException(status_code=422, detail="No updatable fields provided")

    is_privileged = current_user.get("role") in ("admin", "service")

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
            elif not is_privileged:
                existing = await conn.fetchrow(
                    "SELECT submitted_by, status FROM marketplace_plugins WHERE id = $1",
                    plugin_id,
                )
                if existing is None:
                    raise HTTPException(status_code=404, detail="Plugin not found")
                if existing["submitted_by"] != current_user.get("sub"):
                    # Same message as "unknown id" — no reason to reveal that
                    # another developer's submission exists.
                    raise HTTPException(status_code=404, detail="Plugin not found")
                if not (set(updates) <= _OWNER_UPDATABLE):
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "featured can only be changed by an admin "
                            "(status moves through /v1/marketplace/submissions/*)"
                        ),
                    )
                if existing["status"] not in (
                    PluginStatus.DRAFT.value,
                    PluginStatus.REJECTED.value,
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Cannot edit a submission with status "
                            f"'{existing['status']}' — only draft/rejected "
                            f"submissions may be edited by their developer"
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
