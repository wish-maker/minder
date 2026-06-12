# services/plugin-state-manager/core/execution.py
"""
Tool execution engine
"""

import json
import logging
import time
from typing import Any, Dict

import httpx
from models.tool_execution import (
    ToolDiscoveryResponse,
    ToolExecutionRequest,
    ToolExecutionResponse,
    ToolSchema,
)

logger = logging.getLogger(__name__)


async def execute_tool(
    tool_name: str, parameters: Dict[str, Any], user_id: str = "default"
) -> ToolExecutionResponse:
    """
    Execute an AI tool

    Args:
        tool_name: Tool name
        parameters: Tool parameters
        user_id: User ID (for license validation)

    Returns:
        Tool execution result

    Raises:
        HTTPException: If tool not found, not allowed, or execution fails
    """
    start_time = time.time()

    # Get tool details from marketplace
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Get tool info
        tool_response = await client.get(
            f"http://minder-marketplace:8002/v1/marketplace/ai/tools/{tool_name}"
        )

        if tool_response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

        tool_response.raise_for_status()
        tool_data = tool_response.json()

        # Check if tool is active
        if not tool_data.get("active"):
            raise HTTPException(status_code=400, detail=f"Tool {tool_name} is not active")

        # Get plugin name
        plugin_name = tool_data.get("plugin_name")
        plugin_id = tool_data.get("plugin_id")

        # Validate license
        from core.database import get_db_pool
        from core.license import validate_tool_access

        db = await get_db_pool()
        async with db.acquire() as conn:
            license_check = await validate_tool_access(conn, user_id, tool_name)

            if not license_check["allowed"]:
                raise HTTPException(
                    status_code=403,
                    detail={
                        "error": "License tier too low",
                        "tier_required": license_check["tier_required"],
                        "user_tier": license_check["user_tier"],
                        "reason": license_check["reason"],
                    },
                )

        # Check if plugin is enabled
        from core.state import get_plugin_state

        async with db.acquire() as conn:
            plugin_state = await get_plugin_state(conn, plugin_name)

            if not plugin_state:
                raise HTTPException(
                    status_code=404, detail=f"Plugin {plugin_name} not found in state database"
                )

            if plugin_state["state"] != "enabled":
                raise HTTPException(
                    status_code=400,
                    detail=f"Plugin {plugin_name} is not enabled (current state: {plugin_state['state']})",
                )

        # Execute tool via plugin registry
        registry_url = "http://minder-plugin-registry:8001"

        # Build endpoint URL
        tool_endpoint = tool_data.get("endpoint", f"/{tool_name}")
        http_method = tool_data.get("method", "POST")

        execution_url = f"{registry_url}/plugins/{plugin_name}{tool_endpoint}"

        # Execute request
        try:
            if http_method.upper() == "GET":
                response = await client.get(execution_url, params=parameters)
            else:  # POST
                response = await client.post(execution_url, json=parameters)

            response.raise_for_status()

            result = response.json()
            execution_time = time.time() - start_time

            return ToolExecutionResponse(
                tool_name=tool_name,
                plugin_name=plugin_name,
                result=result,
                execution_time=execution_time,
                tier_required=tool_data.get("required_tier", "community"),
            )

        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Tool execution failed: {e.response.text}",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Tool execution error: {str(e)}")


async def discover_tools(
    active_only: bool = True, tier_filter: str = None
) -> ToolDiscoveryResponse:
    """
    Discover all available AI tools

    Args:
        active_only: Only return active tools
        tier_filter: Filter by required tier

    Returns:
        Tool discovery response
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {}
        if active_only:
            params["active_only"] = "true"
        if tier_filter:
            params["tier"] = tier_filter

        response = await client.get(
            "http://minder-marketplace:8002/v1/marketplace/ai/tools", params=params
        )

        response.raise_for_status()
        data = response.json()

        tools = []
        for tool_data in data.get("tools", []):
            # Parse JSON strings for parameters and response_format
            parameters = tool_data.get("parameters", {})
            if isinstance(parameters, str):
                parameters = json.loads(parameters)

            response_format = tool_data.get("response_format", {})
            if isinstance(response_format, str):
                response_format = json.loads(response_format)

            tools.append(
                ToolSchema(
                    name=tool_data["tool_name"],
                    description=tool_data["description"],
                    type=tool_data["type"],
                    parameters=parameters,
                    response_format=response_format,
                    endpoint=tool_data["endpoint"],
                    method=tool_data["method"],
                    required_tier=tool_data["required_tier"],
                )
            )

        return ToolDiscoveryResponse(tools=tools, count=len(tools))


async def discover_plugin_tools(plugin_id: str) -> ToolDiscoveryResponse:
    """
    Discover tools for a specific plugin

    Args:
        plugin_id: Plugin UUID

    Returns:
        Tool discovery response
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"http://minder-marketplace:8002/v1/marketplace/ai/plugins/{plugin_id}/tools"
        )

        response.raise_for_status()
        data = response.json()

        tools = []
        for tool_data in data.get("tools", []):
            # Parse JSON strings for parameters and response_format
            parameters = tool_data.get("parameters", {})
            if isinstance(parameters, str):
                parameters = json.loads(parameters)

            response_format = tool_data.get("response_format", {})
            if isinstance(response_format, str):
                response_format = json.loads(response_format)

            tools.append(
                ToolSchema(
                    name=tool_data["tool_name"],
                    description=tool_data["description"],
                    type=tool_data["type"],
                    parameters=parameters,
                    response_format=response_format,
                    endpoint=tool_data["endpoint"],
                    method=tool_data["method"],
                    required_tier=tool_data["required_tier"],
                )
            )

        return ToolDiscoveryResponse(tools=tools, count=len(tools))
