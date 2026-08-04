# services/marketplace/routes/marketplace.py
import uuid
from typing import Any, List, Optional

from core.database import get_pool
from fastapi import APIRouter, Depends, HTTPException, Query
from models.plugin import PluginCreate, PluginListResponse, PluginResponse, PluginUpdate

from shared.auth.jwt_middleware import get_current_user_or_service

# Columns returned by the plugin SELECT/RETURNING clauses, shared by get/update.
_PLUGIN_COLUMNS = """id, name, display_name, description, author,
                 repository_url, distribution_type, docker_image,
                 current_version, pricing_model, base_tier, status,
                 featured, download_count, rating_average, rating_count,
                 created_at, updated_at, published_at, developer_id, category_id"""

# Fields a PUT /plugins/{id} may change (whitelist → safe to interpolate as column
# names; values always go through bound parameters).
_PLUGIN_UPDATABLE = {
    "display_name",
    "description",
    "pricing_model",
    "base_tier",
    "status",
    "featured",
}


def _row_to_plugin_response(row) -> PluginResponse:
    """Map a marketplace_plugins row to the PluginResponse model."""
    return PluginResponse(
        id=str(row["id"]),
        name=row["name"],
        display_name=row["display_name"],
        description=row["description"],
        author=row["author"],
        author_email=None,
        repository_url=row["repository_url"],
        distribution_type=row["distribution_type"],
        docker_image=row["docker_image"],
        current_version=row["current_version"],
        pricing_model=row["pricing_model"],
        base_tier=row["base_tier"],
        status=row["status"],
        featured=row["featured"],
        download_count=row["download_count"],
        rating_average=(
            float(row["rating_average"]) if row["rating_average"] else None
        ),
        rating_count=row["rating_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        published_at=row["published_at"],
        developer_id=str(row["developer_id"]) if row["developer_id"] else None,
        category_id=str(row["category_id"]) if row["category_id"] else None,
    )


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
    page: int = Query(1, ge=1, description="Deprecated: use limit/offset"),
    page_size: int = Query(
        10, ge=1, le=100, description="Deprecated: use limit/offset"
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

    # Build query conditions
    conditions = []
    params: List[Any] = []
    param_count = 0

    if status:
        param_count += 1
        conditions.append(f"status = ${param_count}")
        params.append(status)

    if category:
        param_count += 1
        conditions.append(f"category_id = ${param_count}")
        params.append(category)

    if pricing_model:
        param_count += 1
        conditions.append(f"pricing_model = ${param_count}")
        params.append(pricing_model)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with pool.acquire() as conn:
        # Get total count
        count_query = f"""
            SELECT COUNT(*)
            FROM marketplace_plugins
            WHERE {where_clause}
        """
        total_count = await conn.fetchval(count_query, *params)

        # Get plugins
        params.extend([eff_limit, eff_offset])

        rows = await conn.fetch(
            f"""
            SELECT id, name, display_name, description, author,
                   repository_url, distribution_type, docker_image,
                   current_version, pricing_model, base_tier, status,
                   featured, download_count, rating_average, rating_count,
                   created_at, updated_at, published_at, developer_id, category_id
            FROM marketplace_plugins
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
            """,
            *params,
        )

        plugins = [_row_to_plugin_response(row) for row in rows]

        return _build_list_response(plugins, total_count, eff_limit, eff_offset)


@router.get("/plugins/search", response_model=PluginListResponse)
async def search_plugins(
    q: str = Query(..., min_length=1),
    limit: Optional[int] = Query(
        None, ge=1, le=100, description="Page size (canonical)"
    ),
    offset: Optional[int] = Query(None, ge=0, description="Items to skip (canonical)"),
    page: int = Query(1, ge=1, description="Deprecated: use limit/offset"),
    page_size: int = Query(
        10, ge=1, le=100, description="Deprecated: use limit/offset"
    ),
):
    """Search plugins by name or description"""
    pool = await get_pool()

    search_pattern = f"%{q}%"
    eff_limit, eff_offset = _resolve_pagination(limit, offset, page, page_size)

    async with pool.acquire() as conn:
        # Get total count
        total_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM marketplace_plugins
            WHERE (name ILIKE $1 OR display_name ILIKE $1 OR description ILIKE $1)
              AND status = 'approved'
            """,
            search_pattern,
        )

        # Get plugins
        rows = await conn.fetch(
            """
            SELECT id, name, display_name, description, author,
                   repository_url, distribution_type, docker_image,
                   current_version, pricing_model, base_tier, status,
                   featured, download_count, rating_average, rating_count,
                   created_at, updated_at, published_at, developer_id, category_id
            FROM marketplace_plugins
            WHERE (name ILIKE $1 OR display_name ILIKE $1 OR description ILIKE $1)
              AND status = 'approved'
            ORDER BY
                CASE WHEN name ILIKE $1 THEN 0 ELSE 1 END,
                download_count DESC
            LIMIT $2 OFFSET $3
            """,
            search_pattern,
            eff_limit,
            eff_offset,
        )

        plugins = [_row_to_plugin_response(row) for row in rows]

        return _build_list_response(plugins, total_count, eff_limit, eff_offset)


@router.post("/plugins", response_model=PluginResponse, status_code=201)
async def create_plugin(
    plugin_data: PluginCreate,
    current_user: dict = Depends(get_current_user_or_service),
):
    """
    Create a new plugin in marketplace

    This endpoint is used internally by the plugin registry to
    automatically register plugins when they are loaded.
    """
    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            # Generate plugin ID
            plugin_id = str(uuid.uuid4())

            # Insert plugin
            row = await conn.fetchrow(
                """
                INSERT INTO marketplace_plugins (
                    id, name, display_name, description, author, author_email,
                    repository_url, distribution_type, docker_image,
                    pricing_model, base_tier, status, developer_id, category_id,
                    download_count, rating_count, featured, created_at, updated_at
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, 0, 0, FALSE, NOW(), NOW()
                )
                RETURNING id, name, display_name, description, author,
                         repository_url, distribution_type, docker_image,
                         current_version, pricing_model, base_tier, status,
                         featured, download_count, rating_average, rating_count,
                         created_at, updated_at, published_at, developer_id, category_id
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
                "approved",  # Auto-approve internally created plugins
                plugin_data.developer_id,
                plugin_data.category_id,
            )

            return _row_to_plugin_response(row)

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create plugin: {str(e)}"
        )


@router.get("/plugins/featured", response_model=PluginListResponse)
async def get_featured_plugins(limit: int = Query(10, ge=1, le=50)):
    """Get featured plugins"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, display_name, description, author,
                   repository_url, distribution_type, docker_image,
                   current_version, pricing_model, base_tier, status,
                   featured, download_count, rating_average, rating_count,
                   created_at, updated_at, published_at, developer_id, category_id
            FROM marketplace_plugins
            WHERE featured = TRUE AND status = 'approved'
            ORDER BY download_count DESC
            LIMIT $1
            """,
            limit,
        )

        plugins = [_row_to_plugin_response(row) for row in rows]

        return PluginListResponse(
            plugins=plugins, count=len(plugins), page=1, page_size=limit, total_pages=1
        )


@router.get("/plugins/{plugin_id}", response_model=PluginResponse)
async def get_plugin(plugin_id: str):
    """Get plugin by ID"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, name, display_name, description, author,
                   repository_url, distribution_type, docker_image,
                   current_version, pricing_model, base_tier, status,
                   featured, download_count, rating_average, rating_count,
                   created_at, updated_at, published_at, developer_id, category_id
            FROM marketplace_plugins
            WHERE id = $1
            """,
            plugin_id,
        )

        if not row:
            raise HTTPException(status_code=404, detail="Plugin not found")

        return _row_to_plugin_response(row)


@router.put("/plugins/{plugin_id}", response_model=PluginResponse)
async def update_plugin(
    plugin_id: str,
    plugin_update: PluginUpdate,
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

    # Column names come from the _PLUGIN_UPDATABLE whitelist (never user input);
    # values are always bound parameters.
    set_clause = ", ".join(f"{col} = ${i}" for i, col in enumerate(updates, start=1))
    params = list(updates.values())
    query = (
        f"UPDATE marketplace_plugins SET {set_clause}, updated_at = NOW() "
        f"WHERE id = ${len(params) + 1} "
        f"RETURNING {_PLUGIN_COLUMNS}"
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, *params, plugin_id)

    if not row:
        raise HTTPException(status_code=404, detail="Plugin not found")

    return _row_to_plugin_response(row)
