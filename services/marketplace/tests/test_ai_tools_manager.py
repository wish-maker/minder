"""
Test AI Tools Manager Service
Tests the AI tools management functionality
"""

import asyncio
import os
import uuid

import pytest

# Set test environment variables BEFORE importing marketplace modules
os.environ.setdefault("MARKETPLACE_DATABASE_HOST", "localhost")
os.environ.setdefault("MARKETPLACE_DATABASE_PORT", "5432")
os.environ.setdefault("MARKETPLACE_DATABASE_USER", "minder")
os.environ.setdefault("MARKETPLACE_DATABASE_PASSWORD", "dev_password_change_me")
os.environ.setdefault("MARKETPLACE_DATABASE_NAME", "minder_marketplace")

from services.marketplace.core.ai_tools_manager import AIToolsManager
from services.marketplace.core.database import close_pool, get_pool


@pytest.fixture(scope="function")
async def cleanup_pool():
    """Ensure database pool is closed after each test"""
    yield
    await close_pool()


@pytest.mark.asyncio
async def test_register_tool_configuration(cleanup_pool):
    """Test registering AI tool configuration"""
    manager = AIToolsManager()
    pool = await get_pool()

    # Create a test plugin first
    async with pool.acquire() as conn:
        plugin_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_plugins
            (name, display_name, description, author, author_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            f"test_plugin_{uuid.uuid4().hex[:8]}",
            "Test Plugin",
            "A test plugin",
            "Test Author",
            "test@example.com",
        )
        plugin_id = str(plugin_result["id"])

    try:
        config_schema = {
            "type": "object",
            "properties": {
                "api_key": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
            },
        }

        default_config = {"api_key": "", "timeout": 30}

        # Register tool configuration
        result = await manager.register_tool_configuration(
            plugin_id=plugin_id,
            tool_name="test_analysis_tool",
            configuration_schema=config_schema,
            default_configuration=default_config,
        )

        assert str(result["plugin_id"]) == plugin_id
        assert result["tool_name"] == "test_analysis_tool"
        assert result["configuration_schema"]["type"] == "object"
        assert "api_key" in result["configuration_schema"]["properties"]

    finally:
        # Clean up
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM marketplace_ai_tools_configurations WHERE plugin_id = $1", plugin_id
            )
            await conn.execute("DELETE FROM marketplace_plugins WHERE id = $1", plugin_id)


@pytest.mark.asyncio
async def test_tool_configuration_validation(cleanup_pool):
    """Test tool configuration validation logic"""
    manager = AIToolsManager()
    pool = await get_pool()

    # Create a test plugin and tool configuration first
    async with pool.acquire() as conn:
        plugin_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_plugins
            (name, display_name, description, author, author_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            f"test_plugin_validate_{uuid.uuid4().hex[:8]}",
            "Test Plugin Validate",
            "A test plugin",
            "Test Author",
            "test@example.com",
        )
        plugin_id = str(plugin_result["id"])

    try:
        config_schema = {
            "type": "object",
            "properties": {"api_key": {"type": "string"}, "timeout": {"type": "integer"}},
            "required": ["api_key"],
        }

        default_config = {"api_key": "default_key", "timeout": 30}

        # Register tool configuration
        await manager.register_tool_configuration(
            plugin_id=plugin_id,
            tool_name="validation_test_tool",
            configuration_schema=config_schema,
            default_configuration=default_config,
            required_parameters={"api_key": {"type": "string"}},
        )

        # Test valid configuration
        valid_config = {"api_key": "test-key", "timeout": 30}

        result = await manager.validate_tool_configuration(
            plugin_id=plugin_id, tool_name="validation_test_tool", configuration=valid_config
        )

        assert result["is_valid"] == True
        assert len(result["errors"]) == 0

        # Test invalid configuration (missing required field)
        invalid_config = {"timeout": 30}

        result = await manager.validate_tool_configuration(
            plugin_id=plugin_id, tool_name="validation_test_tool", configuration=invalid_config
        )

        assert result["is_valid"] == False
        assert len(result["errors"]) > 0

    finally:
        # Clean up
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM marketplace_ai_tools_configurations WHERE plugin_id = $1", plugin_id
            )
            await conn.execute("DELETE FROM marketplace_plugins WHERE id = $1", plugin_id)


@pytest.mark.asyncio
async def test_enable_disable_tool(cleanup_pool):
    """Test enabling and disabling tools"""
    manager = AIToolsManager()
    pool = await get_pool()

    # Create test plugin and installation
    async with pool.acquire() as conn:
        plugin_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_plugins
            (name, display_name, description, author, author_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            f"test_plugin_enable_{uuid.uuid4().hex[:8]}",
            "Test Plugin Enable",
            "A test plugin",
            "Test Author",
            "test@example.com",
        )

        installation_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_installations
            (user_id, plugin_id, status, enabled)
            VALUES ($1, $2, 'installed', TRUE)
            RETURNING id
            """,
            "00000000-0000-0000-0000-000000000001",
            plugin_result["id"],
        )

        plugin_id = str(plugin_result["id"])
        installation_id = str(installation_result["id"])

    try:
        # Create tool configuration
        config_schema = {"type": "object", "properties": {"model": {"type": "string"}}}

        default_config = {"model": "gpt-4"}

        await manager.register_tool_configuration(
            plugin_id=plugin_id,
            tool_name="enable_test_tool",
            configuration_schema=config_schema,
            default_configuration=default_config,
        )

        # Enable tool for installation
        enable_result = await manager.enable_tool_for_installation(
            plugin_id=plugin_id,
            tool_name="enable_test_tool",
            installation_id=installation_id,
            configuration={"model": "gpt-3.5-turbo"},
        )

        assert str(enable_result["plugin_id"]) == plugin_id
        assert enable_result["tool_name"] == "enable_test_tool"
        assert enable_result["is_enabled"] == True
        assert enable_result["activation_status"] == "active"

        # Disable tool
        disable_result = await manager.disable_tool(
            plugin_id=plugin_id, tool_name="enable_test_tool", installation_id=installation_id
        )

        assert disable_result["is_enabled"] == False
        assert disable_result["activation_status"] == "inactive"

    finally:
        # Clean up
        async with pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM marketplace_ai_tools_registrations WHERE plugin_id = $1", plugin_id
            )
            await conn.execute(
                "DELETE FROM marketplace_ai_tools_configurations WHERE plugin_id = $1", plugin_id
            )
            await conn.execute(
                "DELETE FROM marketplace_installations WHERE id = $1", installation_id
            )
            await conn.execute("DELETE FROM marketplace_plugins WHERE id = $1", plugin_id)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
