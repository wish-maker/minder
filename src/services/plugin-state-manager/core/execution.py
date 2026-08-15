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


# JSON-Schema primitive type -> the Python type(s) a validated value must be.
# `bool` is intentionally NOT accepted for integer/number: Python makes `bool` a
# subclass of `int`, so `True` would otherwise satisfy an `integer` parameter.
_JSON_TYPE_PY = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "array": (list,),
    "object": (dict,),
}


def _coerce_scalar(value: Any, declared_type: str) -> Any:
    """Best-effort coerce a string value to its declared scalar JSON type.

    Callers (and, downstream, GET query strings) often send everything as strings,
    e.g. ``"5"`` for a declared ``integer``. Only string inputs are coerced; a value
    already of a non-string type is returned untouched for the isinstance check to
    judge. Raises ``ValueError`` if the string can't represent the declared type."""
    if not isinstance(value, str):
        return value
    if declared_type == "integer":
        return int(value)
    if declared_type == "number":
        return float(value)
    if declared_type == "boolean":
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        raise ValueError(f"{value!r} is not a valid boolean")
    if declared_type in ("array", "object"):
        parsed = json.loads(value)
        return parsed
    return value


def _validate_parameters(
    param_schema: Dict[str, Any], parameters: Dict[str, Any]
) -> Dict[str, Any]:
    """Validate caller ``parameters`` against a tool's declared parameter schema.

    ``param_schema`` is the marketplace-stored ``{param_name: {type, enum?, required?,
    ...}}`` map (see marketplace ai_tools_importer). This is defense-in-depth (#676):
    plugin-state-manager owns the schema and sits between the caller and every plugin
    action, so it rejects a malformed call before it ever reaches a plugin.

    Policy: required-presence, declared ``type`` (with lenient string->scalar
    coercion), and ``enum`` membership are enforced; undeclared/extra keys are left
    alone (some plugin actions accept optional untyped kwargs). Returns the
    (possibly type-coerced) parameters. Raises ``HTTPException(422)`` with per-field
    detail -- matching this codebase's Pydantic-style validation contract -- listing
    every violation, not just the first."""
    if not param_schema:
        # No declared schema (e.g. an empty ``{}``) -> nothing to enforce; forward
        # verbatim, preserving today's permissive behaviour for schemaless tools.
        return parameters

    errors = []
    coerced = dict(parameters)

    # Required-presence.
    for name, spec in param_schema.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("required", False) and name not in parameters:
            errors.append({"field": name, "error": "field required"})

    # Type + enum for every provided, declared parameter.
    for name, value in parameters.items():
        spec = param_schema.get(name)
        if not isinstance(spec, dict):
            continue  # undeclared/extra key -> permissive, forwarded as-is

        declared_type = spec.get("type")
        if declared_type in _JSON_TYPE_PY:
            try:
                value = _coerce_scalar(value, declared_type)
            except (ValueError, TypeError, json.JSONDecodeError):
                errors.append(
                    {"field": name, "error": f"expected type '{declared_type}'"}
                )
                continue
            expected = _JSON_TYPE_PY[declared_type]
            # Exclude bool from int/number even after coercion (bool<:int).
            is_ok = isinstance(value, expected) and not (
                declared_type in ("integer", "number") and isinstance(value, bool)
            )
            if not is_ok:
                errors.append(
                    {"field": name, "error": f"expected type '{declared_type}'"}
                )
                continue
            coerced[name] = value

        allowed = spec.get("enum")
        if isinstance(allowed, list) and value not in allowed:
            errors.append({"field": name, "error": f"must be one of {allowed}"})

    if errors:
        raise HTTPException(status_code=422, detail=errors)

    return coerced


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

        # Reject a malformed call against the tool's own declared schema before it
        # ever reaches the plugin action (#676). parameters_schema is JSONB, which
        # the marketplace serializer may hand back as a dict or a JSON string.
        param_schema = tool_data.get("parameters", {})
        if isinstance(param_schema, str):
            param_schema = json.loads(param_schema)
        parameters = _validate_parameters(param_schema, parameters)

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
            raise HTTPException(
                status_code=500, detail=f"Tool execution error: {str(e)}"
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
