"""
AI Tools Auto-Import Module
Automatically imports AI tools from plugin manifests into the marketplace database
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

import asyncpg

logger = logging.getLogger(__name__)


async def import_ai_tools_from_manifest(
    conn: asyncpg.Connection, plugin_id: str, manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Import AI tools from plugin manifest into marketplace database

    Args:
        conn: Database connection
        plugin_id: UUID of the plugin in marketplace
        manifest: Plugin manifest dictionary

    Returns:
        Import result with tools created/updated
    """
    ai_tools_section = manifest.get("ai_tools")

    if not ai_tools_section:
        return {"success": True, "tools_imported": 0, "message": "No AI tools section in manifest"}

    # Handle both list and dict formats
    if isinstance(ai_tools_section, list):
        tools_data = ai_tools_section
    elif isinstance(ai_tools_section, dict):
        tools_data = ai_tools_section.get("tools", [])
    else:
        return {"success": False, "error": "ai_tools must be a list or dict"}

    imported_count = 0
    errors = []

    for tool_def in tools_data:
        try:
            # Validate required fields
            tool_name = tool_def.get("name")
            if not tool_name:
                errors.append(f"Tool missing 'name' field")
                continue

            # Check if tool already exists
            existing = await conn.fetchrow(
                "SELECT id FROM marketplace_ai_tools WHERE plugin_id = $1 AND tool_name = $2",
                plugin_id,
                tool_name,
            )

            # Build parameters schema
            parameters = tool_def.get("parameters", {})
            parameters_schema = {}
            required_params = []

            for param_name, param_def in parameters.items():
                if not isinstance(param_def, dict):
                    continue

                param_info = {
                    "type": param_def.get("type", "string"),
                    "description": param_def.get("description", ""),
                }

                if "enum" in param_def:
                    param_info["enum"] = param_def["enum"]

                if "default" in param_def:
                    param_info["default"] = param_def["default"]

                parameters_schema[param_name] = param_info

                if param_def.get("required", False):
                    required_params.append(param_name)

            # Build response schema
            response_schema = tool_def.get("response_format", {})

            # Determine tool type
            tool_type = tool_def.get("type", "analysis")
            if tool_type not in ["analysis", "data", "action", "query"]:
                tool_type = "analysis"

            # Determine required tier (default: community)
            required_tier = "community"

            if existing:
                # Update existing tool
                await conn.execute(
                    """
                    UPDATE marketplace_ai_tools
                    SET tool_type = $1,
                        description = $2,
                        endpoint_path = $3,
                        http_method = $4,
                        parameters_schema = $5,
                        response_schema = $6,
                        required_tier = $7,
                        active = TRUE
                    WHERE id = $8
                    """,
                    tool_type,
                    tool_def.get("description", ""),
                    tool_def.get("endpoint", f"/{tool_name}"),
                    tool_def.get("method", "POST"),
                    json.dumps(parameters_schema),
                    json.dumps(response_schema),
                    required_tier,
                    existing["id"],
                )
                logger.info(f"Updated AI tool: {tool_name} for plugin {plugin_id}")
            else:
                # Insert new tool
                await conn.execute(
                    """
                    INSERT INTO marketplace_ai_tools (
                        id, plugin_id, tool_name, tool_type, description,
                        endpoint_path, http_method, parameters_schema,
                        response_schema, required_tier, active
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                    )
                    """,
                    str(uuid.uuid4()),
                    plugin_id,
                    tool_name,
                    tool_type,
                    tool_def.get("description", ""),
                    tool_def.get("endpoint", f"/{tool_name}"),
                    tool_def.get("method", "POST"),
                    json.dumps(parameters_schema),
                    json.dumps(response_schema),
                    required_tier,
                    True,  # active
                )
                logger.info(f"Imported AI tool: {tool_name} for plugin {plugin_id}")

            imported_count += 1

        except Exception as e:
            error_msg = f"Failed to import tool {tool_def.get('name', 'unknown')}: {str(e)}"
            logger.error(error_msg)
            errors.append(error_msg)

    return {
        "success": True,
        "tools_imported": imported_count,
        "errors": errors,
        "message": f"Imported {imported_count} AI tools",
    }


async def deactivate_plugin_ai_tools(conn: asyncpg.Connection, plugin_id: str) -> Dict[str, Any]:
    """
    Deactivate all AI tools for a plugin (when plugin is disabled/uninstalled)

    Args:
        conn: Database connection
        plugin_id: UUID of the plugin

    Returns:
        Deactivation result
    """
    result = await conn.execute(
        "UPDATE marketplace_ai_tools SET active = FALSE, updated_at = NOW() WHERE plugin_id = $1",
        plugin_id,
    )

    # Extract count from result string (format: "UPDATE count")
    count = int(result.split()[-1]) if result else 0

    logger.info(f"Deactivated {count} AI tools for plugin {plugin_id}")

    return {"success": True, "tools_deactivated": count}


async def sync_plugin_tools(
    plugin_name: str, plugin_id: str, manifest: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Synchronize AI tools for a plugin

    This is the main entry point for the auto-import functionality.
    It's called by the plugin registry when a plugin is loaded.

    Args:
        plugin_name: Name of the plugin
        plugin_id: UUID of the plugin in marketplace
        manifest: Plugin manifest dictionary

    Returns:
        Synchronization result
    """
    from services.marketplace.core.database import get_pool

    pool = await get_pool()

    try:
        async with pool.acquire() as conn:
            # Import AI tools from manifest
            result = await import_ai_tools_from_manifest(conn, plugin_id, manifest)

            logger.info(f"AI tools sync completed for {plugin_name}: {result}")
            return result

    except Exception as e:
        logger.error(f"Failed to sync AI tools for {plugin_name}: {e}")
        return {"success": False, "error": str(e), "tools_imported": 0}
