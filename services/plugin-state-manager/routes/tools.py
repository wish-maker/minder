# services/plugin-state-manager/routes/tools.py
"""
Tool discovery and execution endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.execution import (
    discover_plugin_tools,
    discover_tools,
    execute_tool
)
from models.tool_execution import (
    LicenseValidationRequest,
    LicenseValidationResponse,
    ToolDiscoveryResponse,
    ToolExecutionRequest,
    ToolExecutionResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("", response_model=ToolDiscoveryResponse)
async def list_all_tools(
    active_only: bool = Query(True),
    tier: str = Query(None)
):
    """
    List all available AI tools

    Args:
        active_only: Only return active tools
        tier: Filter by required tier
    """
    try:
        return await discover_tools(active_only=active_only, tier_filter=tier)
    except Exception as e:
        logger.error(f"Failed to discover tools: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Tool discovery failed: {str(e)}"
        )


@router.get("/{tool_name}", response_model=ToolDiscoveryResponse)
async def get_tool_details(tool_name: str):
    """Get details for a specific tool"""
    try:
        discovery = await discover_tools()

        # Find the requested tool
        tool = None
        for t in discovery.tools:
            if t.name == tool_name:
                tool = t
                break

        if not tool:
            raise HTTPException(
                status_code=404,
                detail=f"Tool {tool_name} not found"
            )

        return ToolDiscoveryResponse(
            tools=[tool],
            count=1
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tool details for {tool_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get tool details: {str(e)}"
        )


@router.post("/{tool_name}/execute", response_model=ToolExecutionResponse)
async def execute_tool_endpoint(
    tool_name: str,
    request: ToolExecutionRequest,
    user_id: str = Query("default")
):
    """
    Execute an AI tool

    Validates license tier, checks plugin state, and executes tool
    """
    try:
        return await execute_tool(
            tool_name=tool_name,
            parameters=request.parameters,
            user_id=user_id
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to execute tool {tool_name}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Tool execution failed: {str(e)}"
        )


@router.get("/plugins/{plugin_id}/tools", response_model=ToolDiscoveryResponse)
async def list_plugin_tools(plugin_id: str):
    """List all tools for a specific plugin"""
    try:
        return await discover_plugin_tools(plugin_id)
    except Exception as e:
        logger.error(f"Failed to discover tools for plugin {plugin_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to discover plugin tools: {str(e)}"
        )


@router.post("/validate", response_model=LicenseValidationResponse)
async def validate_tool_license(request: LicenseValidationRequest):
    """
    Validate if user has license to access a tool

    Checks user's subscription tier against tool's required tier
    """
    from core.database import get_db_pool
    from core.license import validate_tool_access

    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            result = await validate_tool_access(
                conn,
                request.user_id,
                request.tool_name
            )
            return LicenseValidationResponse(**result)
    except Exception as e:
        logger.error(f"License validation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"License validation failed: {str(e)}"
        )
