# services/plugin-state-manager/routes/state.py
"""
Plugin state management endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.state import (
    disable_plugin,
    enable_plugin,
    get_dependent_plugins,
    get_plugin_state,
    list_plugin_states,
    resolve_dependencies
)
from core.database import get_db_pool
from models.plugin_state import (
    DisablePluginRequest,
    EnablePluginRequest,
    PluginStateListResponse,
    PluginStateResponse,
    UpdatePluginConfigRequest
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/state", response_model=PluginStateListResponse)
async def list_all_plugin_states(
    state: Optional[str] = Query(None)
):
    """List all plugin states"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        states = await list_plugin_states(conn, state)

        return PluginStateListResponse(
            plugins=[PluginStateResponse(**state) for state in states],
            count=len(states)
        )


@router.get("/state/{plugin_name}", response_model=PluginStateResponse)
async def get_plugin_state_by_name(plugin_name: str):
    """Get plugin state by name"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        state = await get_plugin_state(conn, plugin_name)

        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin {plugin_name} not found"
            )

        return PluginStateResponse(**state)


@router.post("/state/{plugin_name}/enable", response_model=PluginStateResponse)
async def enable_plugin_endpoint(
    plugin_name: str,
    request: EnablePluginRequest
):
    """
    Enable a plugin

    - Checks if plugin is required
    - Validates state transitions
    - Updates state to enabled
    """
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            state = await enable_plugin(conn, plugin_name, request.reason)
            return PluginStateResponse(**state)
    except Exception as e:
        logger.error(f"Failed to enable plugin {plugin_name}: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.post("/state/{plugin_name}/disable", response_model=PluginStateResponse)
async def disable_plugin_endpoint(
    plugin_name: str,
    request: DisablePluginRequest
):
    """
    Disable a plugin

    - Checks if plugin is required
    - Validates dependent plugins
    - Updates state to disabled
    """
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            state = await disable_plugin(
                conn,
                plugin_name,
                force=request.force,
                reason=request.reason
            )
            return PluginStateResponse(**state)
    except Exception as e:
        logger.error(f"Failed to disable plugin {plugin_name}: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )


@router.patch("/state/{plugin_name}", response_model=PluginStateResponse)
async def update_plugin_config(
    plugin_name: str,
    request: UpdatePluginConfigRequest
):
    """Update plugin configuration"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        state = await get_plugin_state(conn, plugin_name)

        if not state:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin {plugin_name} not found"
            )

        # Update config
        await conn.execute(
            """
            UPDATE plugin_states
            SET config = $1, metadata = COALESCE($2, metadata), updated_at = NOW()
            WHERE plugin_name = $3
            RETURNING *
            """,
            request.config,
            request.metadata,
            plugin_name
        )

        updated_state = await get_plugin_state(conn, plugin_name)
        return PluginStateResponse(**updated_state)


@router.get("/{plugin_name}/dependencies")
async def get_plugin_dependencies(plugin_name: str):
    """Get plugins that depend on this plugin"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        dependents = await get_dependent_plugins(conn, plugin_name)
        return {
            "plugin_name": plugin_name,
            "dependents": dependents,
            "count": len(dependents)
        }


@router.post("/{plugin_name}/dependencies/resolve")
async def resolve_plugin_dependencies(plugin_name: str):
    """
    Resolve plugin dependencies and return enable order

    Returns ordered list of plugins to enable
    """
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            order = await resolve_dependencies(conn, plugin_name)
            return {
                "plugin_name": plugin_name,
                "enable_order": order,
                "count": len(order)
            }
    except Exception as e:
        logger.error(f"Failed to resolve dependencies for {plugin_name}: {e}")
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
