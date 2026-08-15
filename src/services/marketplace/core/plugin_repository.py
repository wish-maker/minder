"""Plugin catalog queries for the marketplace service.

Extracted from routes/marketplace.py (#492, following the same "thin routes
+ thick core" convention #357/#493/#494 established for rag-pipeline):
list_plugins and search_plugins each hand-built their own WHERE clause
in-line (list_plugins with a manual param_count counter across three optional
filters; search_plugins with an ILIKE search + a CASE WHEN ranking
expression), and get_featured_plugins/get_plugin each duplicated the exact
same 21-column SELECT list a further two times -- despite this file already
defining PLUGIN_COLUMNS as the canonical column list for create_plugin's and
update_plugin's RETURNING clauses. Four inline copies of the same list, only
two of them actually using the constant that already existed for this exact
purpose.

core/database.py stays pool/connection management only; this module holds
the actual query construction + row mapping, taking an already-acquired pool
as a parameter (matching rag-pipeline's core/ingestion.py taking an
already-resolved kb dict rather than looking it up itself).
"""

import json
from typing import Any, List, Optional, Tuple

from models.plugin import PluginResponse

PLUGIN_COLUMNS = """id, name, display_name, description, author,
                 repository_url, distribution_type, docker_image,
                 current_version, pricing_model, base_tier, status,
                 featured, download_count, rating_average, rating_count,
                 created_at, updated_at, published_at, developer_id, category_id, requires_services"""


def row_to_plugin_response(row) -> PluginResponse:
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
        requires_services=json.loads(row["requires_services"] or "[]"),
    )


async def list_plugins_page(
    pool,
    status: Optional[str],
    category: Optional[str],
    pricing_model: Optional[str],
    limit: int,
    offset: int,
) -> Tuple[List[PluginResponse], int]:
    """Query marketplace_plugins with optional status/category/pricing_model
    filters, returning (page of PluginResponse, total_count)."""
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
        total_count = await conn.fetchval(
            f"SELECT COUNT(*) FROM marketplace_plugins WHERE {where_clause}",
            *params,
        )

        params_with_page = params + [limit, offset]
        rows = await conn.fetch(
            f"""
            SELECT {PLUGIN_COLUMNS}
            FROM marketplace_plugins
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_count + 1} OFFSET ${param_count + 2}
            """,
            *params_with_page,
        )

    return [row_to_plugin_response(row) for row in rows], total_count


async def search_plugins_page(
    pool, q: str, limit: int, offset: int
) -> Tuple[List[PluginResponse], int]:
    """Search approved marketplace_plugins by name/display_name/description
    (ILIKE), ranked by exact-name match first then download_count."""
    search_pattern = f"%{q}%"

    async with pool.acquire() as conn:
        total_count = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM marketplace_plugins
            WHERE (name ILIKE $1 OR display_name ILIKE $1 OR description ILIKE $1)
              AND status = 'approved'
            """,
            search_pattern,
        )

        rows = await conn.fetch(
            f"""
            SELECT {PLUGIN_COLUMNS}
            FROM marketplace_plugins
            WHERE (name ILIKE $1 OR display_name ILIKE $1 OR description ILIKE $1)
              AND status = 'approved'
            ORDER BY
                CASE WHEN name ILIKE $2 THEN 0 ELSE 1 END,
                download_count DESC
            LIMIT $3 OFFSET $4
            """,
            # $1 is a substring pattern (for the WHERE filter -- any partial match
            # counts); $2 is the bare query, case-insensitive but no wildcards, so
            # the ranking actually tests for an EXACT name match rather than "the
            # query appears anywhere in name" -- the original CASE reused $1 here,
            # so a more-downloaded partial match (e.g. "supernetwork") could
            # outrank a plugin literally named the search term ("network"),
            # contradicting the documented "exact match first" ranking.
            search_pattern,
            q,
            limit,
            offset,
        )

    return [row_to_plugin_response(row) for row in rows], total_count


async def get_featured_plugins(pool, limit: int) -> List[PluginResponse]:
    """Approved, featured marketplace_plugins ordered by download_count."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {PLUGIN_COLUMNS}
            FROM marketplace_plugins
            WHERE featured = TRUE AND status = 'approved'
            ORDER BY download_count DESC
            LIMIT $1
            """,
            limit,
        )
    return [row_to_plugin_response(row) for row in rows]


async def get_plugin_by_id(pool, plugin_id: str) -> Optional[PluginResponse]:
    """A single marketplace_plugins row by id, or None if it doesn't exist."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {PLUGIN_COLUMNS}
            FROM marketplace_plugins
            WHERE id = $1
            """,
            plugin_id,
        )
    return row_to_plugin_response(row) if row else None
