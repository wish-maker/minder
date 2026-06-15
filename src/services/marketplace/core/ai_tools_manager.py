"""
AI Tools Manager Service
Manages AI tools lifecycle, configuration, and validation
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from jsonschema import ValidationError as JSONSchemaValidationError
from jsonschema import validate

from services.marketplace.core.database import get_pool
from services.marketplace.models.ai_tools import (
    ActivationStatus,
    AIToolConfigurationCreate,
    AIToolRegistrationCreate,
    AIToolResponse,
)

logger = logging.getLogger("minder.marketplace.ai_tools")


class AIToolsManager:
    """Manage AI tools lifecycle"""

    async def register_tool_configuration(
        self,
        plugin_id: str,
        tool_name: str,
        configuration_schema: Dict[str, Any],
        default_configuration: Dict[str, Any],
        required_parameters: Optional[Dict[str, Any]] = None,
        optional_parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Register AI tool configuration schema

        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            configuration_schema: JSON Schema for configuration
            default_configuration: Default configuration values
            required_parameters: Required parameters
            optional_parameters: Optional parameters

        Returns:
            Created configuration
        """
        pool = await get_pool()

        async with pool.acquire() as conn:
            # Check if configuration exists
            existing = await conn.fetchrow(
                """
                SELECT * FROM marketplace_ai_tools_configurations
                WHERE plugin_id = $1 AND tool_name = $2
                """,
                plugin_id,
                tool_name,
            )

            if existing:
                # Update existing
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_configurations
                    SET configuration_schema = $3, default_configuration = $4,
                        required_parameters = $5, optional_parameters = $6, updated_at = NOW()
                    WHERE id = $7
                    RETURNING id, plugin_id, tool_name, configuration_schema, default_configuration
                    """,
                    json.dumps(configuration_schema),
                    json.dumps(default_configuration),
                    json.dumps(required_parameters) if required_parameters else None,
                    json.dumps(optional_parameters) if optional_parameters else None,
                    existing["id"],
                )
            else:
                # Create new
                row = await conn.fetchrow(
                    """
                    INSERT INTO marketplace_ai_tools_configurations
                    (plugin_id, tool_name, configuration_schema, default_configuration,
                     required_parameters, optional_parameters)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id, plugin_id, tool_name, configuration_schema, default_configuration
                    """,
                    plugin_id,
                    tool_name,
                    json.dumps(configuration_schema),
                    json.dumps(default_configuration),
                    json.dumps(required_parameters) if required_parameters else None,
                    json.dumps(optional_parameters) if optional_parameters else None,
                )

            return {
                "id": str(row["id"]),
                "plugin_id": row["plugin_id"],
                "tool_name": row["tool_name"],
                "configuration_schema": json.loads(row["configuration_schema"]),
                "default_configuration": json.loads(row["default_configuration"]),
            }

    async def enable_tool_for_installation(
        self,
        plugin_id: str,
        tool_name: str,
        installation_id: str,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enable AI tool for specific installation

        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            installation_id: Installation ID
            configuration: Tool configuration

        Returns:
            Tool registration details
        """
        pool = await get_pool()

        # Get default configuration if not provided
        if configuration is None:
            async with pool.acquire() as conn:
                config_row = await conn.fetchrow(
                    """
                    SELECT default_configuration
                    FROM marketplace_ai_tools_configurations
                    WHERE plugin_id = $1 AND tool_name = $2
                    """,
                    plugin_id,
                    tool_name,
                )

                if config_row:
                    configuration = json.loads(config_row["default_configuration"])
                else:
                    configuration = {}

        async with pool.acquire() as conn:
            # Check if registration exists
            existing = await conn.fetchrow(
                """
                SELECT * FROM marketplace_ai_tools_registrations
                WHERE plugin_id = $1 AND tool_name = $2 AND installation_id = $3
                """,
                plugin_id,
                tool_name,
                installation_id,
            )

            if existing:
                # Update existing
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET configuration = $4, is_enabled = TRUE, activation_status = 'active',
                        updated_at = NOW()
                    WHERE id = $5
                    RETURNING id, plugin_id, tool_name, installation_id, configuration,
                             is_enabled, activation_status
                    """,
                    json.dumps(configuration),
                    existing["id"],
                )
            else:
                # Create new
                row = await conn.fetchrow(
                    """
                    INSERT INTO marketplace_ai_tools_registrations
                    (plugin_id, tool_name, installation_id, configuration, is_enabled, activation_status)
                    VALUES ($1, $2, $3, $4, TRUE, 'active')
                    RETURNING id, plugin_id, tool_name, installation_id, configuration,
                             is_enabled, activation_status
                    """,
                    plugin_id,
                    tool_name,
                    installation_id,
                    json.dumps(configuration),
                )

            return {
                "id": str(row["id"]),
                "plugin_id": row["plugin_id"],
                "tool_name": row["tool_name"],
                "installation_id": row["installation_id"],
                "configuration": json.loads(row["configuration"]),
                "is_enabled": row["is_enabled"],
                "activation_status": row["activation_status"],
            }

    async def disable_tool(
        self, plugin_id: str, tool_name: str, installation_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Disable AI tool

        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            installation_id: Optional installation ID (if None, disable for all)

        Returns:
            Updated tool status
        """
        pool = await get_pool()

        async with pool.acquire() as conn:
            if installation_id:
                # Disable for specific installation
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET is_enabled = FALSE, activation_status = 'inactive', updated_at = NOW()
                    WHERE plugin_id = $1 AND tool_name = $2 AND installation_id = $3
                    RETURNING id, is_enabled, activation_status
                    """,
                    plugin_id,
                    tool_name,
                    installation_id,
                )
            else:
                # Disable for all installations
                row = await conn.fetchrow(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET is_enabled = FALSE, activation_status = 'inactive', updated_at = NOW()
                    WHERE plugin_id = $1 AND tool_name = $2
                    RETURNING id, is_enabled, activation_status
                    """,
                    plugin_id,
                    tool_name,
                )

            if not row:
                raise ValueError(f"Tool registration not found: {plugin_id}/{tool_name}")

            return {
                "id": str(row["id"]),
                "is_enabled": row["is_enabled"],
                "activation_status": row["activation_status"],
            }

    async def validate_tool_configuration(
        self, plugin_id: str, tool_name: str, configuration: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate tool configuration against schema

        Args:
            plugin_id: Plugin ID
            tool_name: Tool name
            configuration: Configuration to validate

        Returns:
            Validation result
        """
        pool = await get_pool()

        async with pool.acquire() as conn:
            # Get configuration schema
            row = await conn.fetchrow(
                """
                SELECT configuration_schema, required_parameters
                FROM marketplace_ai_tools_configurations
                WHERE plugin_id = $1 AND tool_name = $2
                """,
                plugin_id,
                tool_name,
            )

            if not row:
                return {"is_valid": False, "errors": ["Configuration schema not found"]}

            schema = json.loads(row["configuration_schema"])
            required_params = (
                json.loads(row["required_parameters"]) if row["required_parameters"] else {}
            )

            # Validate against schema
            try:
                validate(instance=configuration, schema=schema)

                # Check required parameters
                missing_params = []
                for param_name in required_params.keys():
                    if param_name not in configuration:
                        missing_params.append(param_name)

                if missing_params:
                    return {
                        "is_valid": False,
                        "errors": [f"Missing required parameters: {', '.join(missing_params)}"],
                    }

                # Update validation status in database
                await conn.execute(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET validation_status = 'valid', last_validated_at = NOW(),
                        validation_errors = NULL
                    WHERE plugin_id = $1 AND tool_name = $2
                    """,
                    plugin_id,
                    tool_name,
                )

                return {"is_valid": True, "errors": []}

            except JSONSchemaValidationError as e:
                errors = [str(e.message)]

                # Update validation status in database
                await conn.execute(
                    """
                    UPDATE marketplace_ai_tools_registrations
                    SET validation_status = 'invalid', last_validated_at = NOW(),
                        validation_errors = $3
                    WHERE plugin_id = $1 AND tool_name = $2
                    """,
                    plugin_id,
                    tool_name,
                    json.dumps(errors),
                )

                return {"is_valid": False, "errors": errors}

    async def get_tools_for_plugin(
        self, plugin_id: str, include_disabled: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Get all tools for a plugin

        Args:
            plugin_id: Plugin ID
            include_disabled: Include disabled tools

        Returns:
            List of tools
        """
        pool = await get_pool()

        async with pool.acquire() as conn:
            query = """
                SELECT
                    at.id, at.plugin_id, at.tool_name, at.tool_type, at.description,
                    at.endpoint_path, at.http_method, at.parameters_schema, at.response_schema,
                    at.required_tier, at.is_enabled, at.category, at.tags,
                    at.configuration_schema, at.default_configuration,
                    p.name as plugin_name
                FROM marketplace_ai_tools at
                JOIN marketplace_plugins p ON at.plugin_id = p.id
                WHERE at.plugin_id = $1
            """

            if not include_disabled:
                query += " AND at.is_enabled = TRUE"

            query += " ORDER BY at.tool_name"

            rows = await conn.fetch(query, plugin_id)

            tools = []
            for row in rows:
                tools.append(
                    {
                        "id": str(row["id"]),
                        "plugin_id": str(row["plugin_id"]),
                        "plugin_name": row["plugin_name"],
                        "tool_name": row["tool_name"],
                        "type": row["tool_type"],
                        "description": row["description"],
                        "endpoint": row["endpoint_path"],
                        "method": row["http_method"],
                        "parameters": row["parameters_schema"],
                        "response_format": row["response_schema"],
                        "required_tier": row["required_tier"],
                        "is_enabled": row["is_enabled"],
                        "category": row["category"],
                        "tags": row["tags"],
                        "configuration_schema": (
                            json.loads(row["configuration_schema"])
                            if row["configuration_schema"]
                            else None
                        ),
                        "default_configuration": (
                            json.loads(row["default_configuration"])
                            if row["default_configuration"]
                            else None
                        ),
                    }
                )

            return tools

    async def get_all_ai_tools(
        self, active_only: bool = True, category: Optional[str] = None, tier: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all AI tools across all plugins

        Args:
            active_only: Only return active tools
            category: Filter by category
            tier: Filter by required tier

        Returns:
            Dictionary with tools list and count
        """
        pool = await get_pool()

        query = """
            SELECT
                at.id, at.plugin_id, at.tool_name, at.tool_type, at.description,
                at.endpoint_path, at.http_method, at.parameters_schema, at.response_schema,
                at.required_tier, at.is_enabled, at.category, at.tags,
                p.name as plugin_name, p.display_name as plugin_display_name
            FROM marketplace_ai_tools at
            JOIN marketplace_plugins p ON at.plugin_id = p.id
            WHERE $1
            ORDER BY p.name, at.tool_name
        """

        # Build conditions
        conditions = []
        params = []
        param_count = 0

        if active_only:
            param_count += 1
            conditions.append(f"at.is_enabled = ${param_count}")
            params.append(True)

        if category:
            param_count += 1
            conditions.append(f"at.category = ${param_count}")
            params.append(category)

        if tier:
            param_count += 1
            conditions.append(f"at.required_tier = ${param_count}")
            params.append(tier)

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        async with pool.acquire() as conn:
            final_query = query.replace("$1", where_clause)
            rows = await conn.fetch(final_query, *params)

            tools = []
            for row in rows:
                tools.append(
                    {
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
                        "is_enabled": row["is_enabled"],
                        "category": row["category"],
                        "tags": row["tags"],
                    }
                )

            return {"tools": tools, "count": len(tools)}
