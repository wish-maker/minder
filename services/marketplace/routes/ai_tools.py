# services/marketplace/routes/ai_tools.py
import logging
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.marketplace.core.ai_tools_importer import sync_plugin_tools
from services.marketplace.core.database import get_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/marketplace/ai", tags=["AI Tools"])


class AIToolsSyncRequest(BaseModel):
    """Request model for syncing AI tools from plugin manifest"""
    plugin_name: str
    plugin_id: str
    manifest: Dict


@router.get("/tools")
async def list_all_ai_tools(
    active_only: bool = Query(True),
    tier: str = Query(None)
):
    """
    List all AI tools from all plugins

    Args:
        active_only: Only return active tools
        tier: Filter by required tier
    """
    pool = await get_pool()

    # Build query conditions
    conditions = []
    params = []
    param_count = 0

    if active_only:
        param_count += 1
        conditions.append(f"at.active = ${param_count}")
        params.append(True)

    if tier:
        param_count += 1
        conditions.append(f"at.required_tier = ${param_count}")
        params.append(tier)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT
                at.id,
                at.plugin_id,
                at.tool_name,
                at.tool_type,
                at.description,
                at.endpoint_path,
                at.http_method,
                at.parameters_schema,
                at.response_schema,
                at.required_tier,
                at.active,
                p.name as plugin_name,
                p.display_name as plugin_display_name
            FROM marketplace_ai_tools at
            JOIN marketplace_plugins p ON at.plugin_id = p.id
            WHERE {where_clause}
            ORDER BY p.name, at.tool_name
            """,
            *params
        )

        tools = []
        for row in rows:
            tools.append({
                "id": str(row["id"]),
                "plugin_id": str(row["plugin_id"]),
                "plugin_name": row["plugin_name"],
                "plugin_display_name": row["plugin_display_name"],
                "tool_name": row["tool_name"],
                "type": row["tool_type"],
                "description": row["description"],
                "endpoint": row["endpoint_path"],
                "method": row["http_method"],
                "parameters": row["parameters_schema"],
                "response_format": row["response_schema"],
                "required_tier": row["required_tier"],
                "active": row["active"]
            })

        return {
            "tools": tools,
            "count": len(tools)
        }


@router.get("/plugins/{plugin_id}/tools")
async def get_plugin_ai_tools(plugin_id: str):
    """Get all AI tools for a specific plugin"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Check if plugin exists
        plugin = await conn.fetchrow(
            "SELECT * FROM marketplace_plugins WHERE id = $1",
            plugin_id
        )

        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")

        # Get AI tools
        rows = await conn.fetch(
            """
            SELECT
                id, tool_name, tool_type, description,
                endpoint_path, http_method, parameters_schema,
                response_schema, required_tier, active
            FROM marketplace_ai_tools
            WHERE plugin_id = $1 AND active = TRUE
            ORDER BY tool_name
            """,
            plugin_id
        )

        tools = []
        for row in rows:
            tools.append({
                "id": str(row["id"]),
                "tool_name": row["tool_name"],
                "type": row["tool_type"],
                "description": row["description"],
                "endpoint": row["endpoint_path"],
                "method": row["http_method"],
                "parameters": row["parameters_schema"],
                "response_format": row["response_schema"],
                "required_tier": row["required_tier"],
                "active": row["active"]
            })

        return {
            "plugin_id": plugin_id,
            "plugin_name": plugin["name"],
            "tools": tools,
            "count": len(tools)
        }


@router.get("/tools/{tool_name}")
async def get_ai_tool_details(tool_name: str):
    """Get details for a specific AI tool"""
    pool = await get_pool()

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                at.id,
                at.plugin_id,
                at.tool_name,
                at.tool_type,
                at.description,
                at.endpoint_path,
                at.http_method,
                at.parameters_schema,
                at.response_schema,
                at.required_tier,
                at.active,
                p.name as plugin_name,
                p.display_name as plugin_display_name,
                p.description as plugin_description
            FROM marketplace_ai_tools at
            JOIN marketplace_plugins p ON at.plugin_id = p.id
            WHERE at.tool_name = $1
            """,
            tool_name
        )

        if not row:
            raise HTTPException(status_code=404, detail="AI tool not found")

        return {
            "id": str(row["id"]),
            "plugin_id": str(row["plugin_id"]),
            "plugin_name": row["plugin_name"],
            "plugin_display_name": row["plugin_display_name"],
            "plugin_description": row["plugin_description"],
            "tool_name": row["tool_name"],
            "type": row["tool_type"],
            "description": row["description"],
            "endpoint": row["endpoint_path"],
            "method": row["http_method"],
            "parameters": row["parameters_schema"],
            "response_format": row["response_schema"],
            "required_tier": row["required_tier"],
            "active": row["active"]
        }


@router.post("/sync")
async def sync_ai_tools(request: AIToolsSyncRequest):
    """
    Sync AI tools from plugin manifest

    This endpoint is called by the plugin registry when a plugin is loaded.
    It automatically imports/updates AI tools defined in the plugin's manifest.yml.

    Args:
        request: Sync request with plugin_name, plugin_id, and manifest

    Returns:
        Sync result with tools imported/updated
    """
    try:
        result = await sync_plugin_tools(
            plugin_name=request.plugin_name,
            plugin_id=request.plugin_id,
            manifest=request.manifest
        )

        return result

    except Exception as e:
        logger.error(f"AI tools sync failed for {request.plugin_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to sync AI tools: {str(e)}"
        )


@router.delete("/plugins/{plugin_id}/tools")
async def deactivate_plugin_tools(plugin_id: str):
    """
    Deactivate all AI tools for a plugin

    Called when a plugin is disabled or uninstalled.
    """
    from services.marketplace.core.ai_tools_importer import deactivate_plugin_ai_tools

    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            result = await deactivate_plugin_ai_tools(conn, plugin_id)
            return result

    except Exception as e:
        logger.error(f"Failed to deactivate tools for plugin {plugin_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to deactivate tools: {str(e)}"
        )
