# services/plugin-state-manager/routes/state.py
"""
Plugin state management endpoints
"""

import json
import logging
from typing import Optional

from core.database import get_db_pool
from core.state import (
    PluginNotFoundError,
    RequiredPluginError,
    StateTransitionError,
    disable_plugin,
    enable_plugin,
    get_dependent_plugins,
    get_plugin_state,
    list_plugin_states,
    plugin_exists_in_registry,
    resolve_dependencies,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from models.plugin_state import (
    DisablePluginRequest,
    EnablePluginRequest,
    PluginState,
    PluginStateListResponse,
    PluginStateResponse,
    UpdatePluginConfigRequest,
)

from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error
from shared.pagination import paginate

logger = logging.getLogger(__name__)

router = APIRouter()


def _http_from_domain_error(
    action: str, plugin_name: str, e: Exception
) -> HTTPException:
    """Map a state-layer exception to the right HTTP status.

    Domain errors are client-facing (404 not-found, 409 conflict); anything
    else is a server fault and must surface as 500, not a masked 400.
    """
    if isinstance(e, PluginNotFoundError):
        return HTTPException(status_code=404, detail=str(e))
    if isinstance(e, (RequiredPluginError, StateTransitionError)):
        return HTTPException(status_code=409, detail=str(e))
    logger.error(f"Failed to {action} plugin {plugin_name}: {e}")
    return HTTPException(
        status_code=500, detail=f"Internal error trying to {action} plugin"
    )


@router.get("/state", response_model=PluginStateListResponse)
async def list_all_plugin_states(
    state: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List all plugin states (optional ?state= filter), paginated (#147/C6)."""
    try:
        state_filter = PluginState(state) if state else None
    except ValueError:
        valid = ", ".join(s.value for s in PluginState)
        raise HTTPException(
            status_code=422,
            detail=f"Invalid state '{state}'. Valid values: {valid}",
        )
    db = await get_db_pool()

    async with db.acquire() as conn:
        states = await list_plugin_states(conn, state_filter)

        page, total = paginate(states, limit, offset)
        return PluginStateListResponse(
            plugins=[PluginStateResponse(**s) for s in page],
            count=len(page),
            total=total,
            limit=limit,
            offset=offset,
        )


@router.get("/state/{plugin_name}", response_model=PluginStateResponse)
async def get_plugin_state_by_name(plugin_name: str):
    """Get plugin state by name"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        state = await get_plugin_state(conn, plugin_name)

        if not state:
            raise HTTPException(
                status_code=404, detail=f"Plugin {plugin_name} not found"
            )

        return PluginStateResponse(**state)


@router.post("/state/{plugin_name}/enable", response_model=PluginStateResponse)
async def enable_plugin_endpoint(
    plugin_name: str,
    request: EnablePluginRequest,
    current_user: dict = Depends(get_current_user_or_service),
):
    """
    Enable a plugin

    - Checks if plugin is required
    - Validates state transitions
    - Updates state to enabled

    #751: a plugin with no state row yet (never in default_plugins.yml's bootstrap
    list) gets ONE retry with allow_create=True, but only after plugin-registry
    itself confirms the plugin exists -- see plugin_exists_in_registry's docstring
    for why that check matters.
    """
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            state = await enable_plugin(conn, plugin_name, request.reason)
            return PluginStateResponse(**state)
    except PluginNotFoundError:
        try:
            exists = await plugin_exists_in_registry(plugin_name)
        except Exception as e:
            logger.error(
                f"Could not verify plugin {plugin_name!r} with plugin-registry: {e}"
            )
            raise backend_http_error(e, "Plugin existence check")
        if not exists:
            raise HTTPException(
                status_code=404, detail=f"Plugin {plugin_name} not found"
            )
        try:
            async with db.acquire() as conn:
                state = await enable_plugin(
                    conn, plugin_name, request.reason, allow_create=True
                )
                return PluginStateResponse(**state)
        except Exception as e:
            raise _http_from_domain_error("enable", plugin_name, e)
    except Exception as e:
        raise _http_from_domain_error("enable", plugin_name, e)


@router.post("/state/{plugin_name}/disable", response_model=PluginStateResponse)
async def disable_plugin_endpoint(
    plugin_name: str,
    request: DisablePluginRequest,
    current_user: dict = Depends(get_current_user_or_service),
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
                conn, plugin_name, force=request.force, reason=request.reason
            )
            return PluginStateResponse(**state)
    except Exception as e:
        raise _http_from_domain_error("disable", plugin_name, e)


@router.patch("/state/{plugin_name}", response_model=PluginStateResponse)
async def update_plugin_config(
    plugin_name: str,
    request: UpdatePluginConfigRequest,
    current_user: dict = Depends(get_current_user_or_service),
):
    """Update plugin configuration"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        state = await get_plugin_state(conn, plugin_name)

        if not state:
            raise HTTPException(
                status_code=404, detail=f"Plugin {plugin_name} not found"
            )

        # Update config. asyncpg has no codec registered for jsonb (shared/db/pool.py
        # calls plain asyncpg.create_pool()), so a bound dict param must be
        # pre-serialized -- passing request.config as-is raises asyncpg.DataError
        # ("a dict is not a str"). Matches plugin-registry's core/database.py
        # convention for the same kind of write.
        await conn.execute(
            """
            UPDATE plugin_states
            SET config = $1, updated_at = NOW()
            WHERE plugin_name = $2
            """,
            json.dumps(request.config),
            plugin_name,
        )

        updated_state = await get_plugin_state(conn, plugin_name)
        return PluginStateResponse(**(updated_state or {}))


@router.get("/{plugin_name}/dependencies")
async def get_plugin_dependencies(plugin_name: str):
    """Get plugins that depend on this plugin"""
    db = await get_db_pool()

    async with db.acquire() as conn:
        dependents = await get_dependent_plugins(conn, plugin_name)
        return {
            "plugin_name": plugin_name,
            "dependents": dependents,
            "count": len(dependents),
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
                "count": len(order),
            }
    except Exception as e:
        raise _http_from_domain_error("resolve dependencies for", plugin_name, e)
