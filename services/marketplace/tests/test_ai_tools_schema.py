"""
Test AI Tools Enhanced Schema
Tests the enhanced database schema for AI tools management
"""

import pytest
import asyncpg
import json
from typing import List


@pytest.mark.asyncio
async def test_ai_tools_enhanced_schema():
    """Test that AI tools enhancements are applied correctly"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="minder",
        password="dev_password_change_me",
        database="minder_marketplace"
    )

    try:
        # Check new AI tools tables exist
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND (table_name LIKE 'marketplace_ai%' OR table_name LIKE '%ai%')
            ORDER BY table_name
        """)

        table_names = [row['table_name'] for row in tables]

        # New AI tools tables
        assert 'marketplace_ai_tools_configurations' in table_names
        assert 'marketplace_ai_tools_registrations' in table_names
        assert 'marketplace_plugin_ai_tools' in table_names

        # Check enhanced columns in marketplace_ai_tools
        columns = await conn.fetch("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'marketplace_ai_tools'
            ORDER BY column_name
        """)

        column_names = [row['column_name'] for row in columns]

        # Enhanced columns
        assert 'configuration_schema' in column_names
        assert 'default_configuration' in column_names
        assert 'is_enabled' in column_names
        assert 'required_tier' in column_names
        assert 'category' in column_names
        assert 'tags' in column_names
        assert 'requires_configuration' in column_names
        assert 'allow_user_configuration' in column_names

        # Check indexes
        indexes = await conn.fetch("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND (indexname LIKE 'ai_%' OR indexname LIKE '%ai%')
            ORDER BY indexname
        """)

        index_names = [row['indexname'] for row in indexes]
        assert len(index_names) > 0

        print(f"✅ AI tools schema validated successfully")
        print(f"   - Tables found: {len(table_names)}")
        print(f"   - Enhanced columns: {len(column_names)}")
        print(f"   - Indexes created: {len(index_names)}")

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_ai_tools_configuration_table():
    """Test AI tools configuration table structure"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="minder",
        password="dev_password_change_me",
        database="minder_marketplace"
    )

    try:
        # First create a test plugin
        import uuid
        plugin_result = await conn.fetchrow("""
            INSERT INTO marketplace_plugins
            (name, display_name, description, author, author_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """,
        f"test_plugin_{uuid.uuid4().hex[:8]}", "Test Plugin", "A test plugin", "Test Author", "test@example.com"
        )

        plugin_id = plugin_result["id"]

        # Test inserting a tool configuration
        result = await conn.fetchrow("""
            INSERT INTO marketplace_ai_tools_configurations
            (plugin_id, tool_name, configuration_schema, default_configuration)
            VALUES ($1, $2, $3, $4)
            RETURNING id, tool_name, configuration_schema, default_configuration
        """,
        plugin_id,
        "test_tool",
        json.dumps({"type": "object", "properties": {"api_key": {"type": "string"}}}),
        json.dumps({"api_key": "default_key"})
        )

        assert result["tool_name"] == "test_tool"

        # Parse the JSONB configuration_schema
        config_schema = json.loads(result["configuration_schema"])
        assert config_schema["type"] == "object"

        # Clean up
        await conn.execute("DELETE FROM marketplace_ai_tools_configurations WHERE tool_name = 'test_tool'")
        await conn.execute("DELETE FROM marketplace_plugins WHERE name LIKE 'test_plugin_%'")

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_ai_tools_constraints():
    """Test AI tools constraints and validations"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="minder",
        password="dev_password_change_me",
        database="minder_marketplace"
    )

    try:
        # First create test data
        import uuid
        plugin_result = await conn.fetchrow("""
            INSERT INTO marketplace_plugins
            (name, display_name, description, author, author_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """,
        f"test_plugin_constraints_{uuid.uuid4().hex[:8]}", "Test Plugin Constraints", "A test plugin", "Test Author", "test@example.com"
        )

        installation_result = await conn.fetchrow("""
            INSERT INTO marketplace_installations
            (user_id, plugin_id, status, enabled)
            VALUES ($1, $2, 'installed', TRUE)
            RETURNING id
        """,
        "00000000-0000-0000-0000-000000000001",
        plugin_result["id"]
        )

        # Test activation_status constraint
        valid_statuses = ['pending', 'active', 'inactive', 'error']

        for status in valid_statuses:
            # Should not raise error for valid statuses
            await conn.execute("""
                INSERT INTO marketplace_ai_tools_registrations
                (plugin_id, tool_name, installation_id, configuration, activation_status)
                VALUES ($1, $2, $3, $4, $5)
            """,
            plugin_result["id"],
            f"test_tool_{status}",
            installation_result["id"],
            json.dumps({}),
            status
            )

        # Clean up
        await conn.execute("""
            DELETE FROM marketplace_ai_tools_registrations
            WHERE tool_name LIKE 'test_tool_%'
        """)
        await conn.execute("DELETE FROM marketplace_installations WHERE user_id = '00000000-0000-0000-0000-000000000001'")
        await conn.execute("DELETE FROM marketplace_plugins WHERE name LIKE 'test_plugin_constraints_%'")

        print("✅ AI tools constraints validated successfully")

    finally:
        await conn.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_ai_tools_enhanced_schema())