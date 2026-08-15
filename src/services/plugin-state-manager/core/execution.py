# services/plugin-state-manager/core/execution.py
"""
Tool execution engine
"""

import json
import logging
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import HTTPException
from models.tool_execution import (
    ToolDiscoveryResponse,
    ToolExecutionResponse,
    ToolSchema,
)

from config import settings

logger = logging.getLogger(__name__)


def _row_to_tool_schema(tool_data: Dict[str, Any]) -> ToolSchema:
    """Build a ToolSchema from a marketplace AI-tools row.

    parameters/response_format arrive as either dicts or JSON strings depending on
    the marketplace serializer, so normalise both. Shared by the two discovery
    endpoints below (they carried a byte-identical copy of this loop body)."""
    parameters = tool_data.get("parameters", {})
    if isinstance(parameters, str):
        parameters = json.loads(parameters)

    response_format = tool_data.get("response_format", {})
    if isinstance(response_format, str):
        response_format = json.loads(response_format)

    return ToolSchema(
        name=tool_data["tool_name"],
        description=tool_data["description"],
        type=tool_data["type"],
        parameters=parameters,
        response_format=response_format,
        endpoint=tool_data["endpoint"],
        method=tool_data["method"],
        required_tier=tool_data["required_tier"],
    )


_PARAMETER_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _validate_parameters(tool_schema: ToolSchema, parameters: Dict[str, Any]) -> None:
    """Reject a call against the tool's own declared schema before it's ever
    forwarded to a plugin action (#676) -- today nothing here does, so a
    missing required field, wrong type, or enum-violating value is forwarded
    verbatim. Collects every violation (matching plugin-registry's
    validate_manifest/#147 "detail": [...] convention) rather than stopping at
    the first, and stays permissive on extra/undeclared keys -- some plugin
    actions accept optional untyped kwargs, and this schema isn't necessarily
    exhaustive.

    An undeclared/unrecognised `type` string (schemas are marketplace-authored,
    not a fixed enum) skips the type check for that parameter rather than
    rejecting the call -- the required/enum checks still apply."""
    errors = []
    for name, param in tool_schema.parameters.items():
        if name not in parameters:
            if param.required:
                errors.append(f"'{name}' is required")
            continue

        value = parameters[name]
        expected_type = _PARAMETER_TYPE_MAP.get(param.type)
        if expected_type is not None:
            # bool is a subclass of int in Python -- a JSON boolean must not
            # satisfy an "integer"/"number" parameter.
            if param.type in ("integer", "number") and isinstance(value, bool):
                errors.append(f"'{name}' must be of type {param.type}, got boolean")
            elif not isinstance(value, expected_type):
                errors.append(
                    f"'{name}' must be of type {param.type}, got {type(value).__name__}"
                )

        if param.enum and value not in param.enum:
            errors.append(f"'{name}' must be one of {param.enum}, got {value!r}")

    if errors:
        raise HTTPException(status_code=422, detail=errors)


def _build_execution_url(
    registry_url: str, plugin_name: str, tool_endpoint: str
) -> str:
    """Plugin-registry's real actions route is versioned
    (`/v1/plugins/{name}/actions/{action}`, routes/plugins.py) but
    `tool_endpoint` (marketplace's `endpoint_path`, e.g. "/actions/get_weather")
    is a RELATIVE path with no version prefix baked in -- the `/v1` segment has
    to be added here. Split out as a pure function (no lazy DB/license imports)
    so it's testable on its own; `execute_tool` below has real imports that make
    it deliberately excluded from this service's isolated-import test harness."""
    return f"{registry_url}/v1/plugins/{plugin_name}{tool_endpoint}"


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

    # Get tool details from marketplace. This client also wraps the actual tool
    # execution below, so it uses the generous tool-execution timeout (a real tool
    # may do work); the marketplace lookup itself returns fast within it.
    async with httpx.AsyncClient(timeout=settings.TOOL_EXECUTION_TIMEOUT) as client:
        # Get tool info
        tool_response = await client.get(
            f"{settings.MARKETPLACE_URL}/v1/marketplace/ai/tools/{tool_name}"
        )

        if tool_response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Tool {tool_name} not found")

        tool_response.raise_for_status()
        tool_data = tool_response.json()

        # Check if tool is active
        if not tool_data.get("active"):
            raise HTTPException(
                status_code=400, detail=f"Tool {tool_name} is not active"
            )

        # Reject a malformed call against the tool's own declared schema before
        # any of the (more expensive) license/state checks or the actual
        # downstream dispatch (#676).
        _validate_parameters(_row_to_tool_schema(tool_data), parameters)

        # Get plugin name
        plugin_name = tool_data.get("plugin_name")
        # plugin_id = tool_data.get("plugin_id")  # Not currently used

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
                    status_code=404,
                    detail=f"Plugin {plugin_name} not found in state database",
                )

            if plugin_state["state"] != "enabled":
                raise HTTPException(
                    status_code=400,
                    detail=f"Plugin {plugin_name} is not enabled (current state: {plugin_state['state']})",
                )

        # Execute tool via plugin registry
        registry_url = settings.PLUGIN_REGISTRY_URL

        tool_endpoint = tool_data.get("endpoint", f"/{tool_name}")
        http_method = tool_data.get("method", "POST")

        execution_url = _build_execution_url(registry_url, plugin_name, tool_endpoint)

        # Execute request. A dispatch failure (httpx.HTTPStatusError from
        # raise_for_status(), a connection error, anything) is deliberately left
        # to propagate uncaught here -- every OTHER handler in this module (and
        # in routes/tools.py, which already wraps this call in
        # `except Exception as e: raise backend_http_error(e, "Tool execution")`)
        # sanitizes failures the same way. This function used to catch these two
        # cases itself and raise a raw HTTPException carrying the downstream
        # plugin's full, untouched response body (e.response.text) or a bare
        # str(exc) -- bypassing that convention and leaking whatever a plugin
        # action's error response/traceback happened to contain, plus turning a
        # connectivity failure into a plain 500 instead of the platform's
        # retryable 503.
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


async def discover_tools(
    active_only: bool = True, tier_filter: Optional[str] = None
) -> ToolDiscoveryResponse:
    """
    Discover all available AI tools

    Args:
        active_only: Only return active tools
        tier_filter: Filter by required tier

    Returns:
        Tool discovery response
    """
    async with httpx.AsyncClient(timeout=settings.CATALOG_HTTP_TIMEOUT) as client:
        params = {}
        if active_only:
            params["active_only"] = "true"
        if tier_filter:
            params["tier"] = tier_filter

        response = await client.get(
            f"{settings.MARKETPLACE_URL}/v1/marketplace/ai/tools", params=params
        )

        response.raise_for_status()
        data = response.json()

        tools = [_row_to_tool_schema(t) for t in data.get("tools", [])]
        return ToolDiscoveryResponse(tools=tools, count=len(tools))


async def discover_plugin_tools(plugin_id: str) -> ToolDiscoveryResponse:
    """
    Discover tools for a specific plugin

    Args:
        plugin_id: Plugin UUID

    Returns:
        Tool discovery response
    """
    async with httpx.AsyncClient(timeout=settings.CATALOG_HTTP_TIMEOUT) as client:
        response = await client.get(
            f"{settings.MARKETPLACE_URL}/v1/marketplace/ai/plugins/{plugin_id}/tools"
        )

        # A plugin absent from the catalog makes marketplace return 404. Surface that
        # as our own clean 404 rather than letting raise_for_status() bubble an
        # httpx.HTTPStatusError up to the route's generic handler, which turned every
        # unknown-plugin lookup into a 500 (#576).
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="Plugin not found")

        response.raise_for_status()
        data = response.json()

        tools = [_row_to_tool_schema(t) for t in data.get("tools", [])]
        return ToolDiscoveryResponse(tools=tools, count=len(tools))
