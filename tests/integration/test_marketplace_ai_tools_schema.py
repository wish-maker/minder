"""
Test AI Tools Enhanced Schema
Tests the enhanced database schema for AI tools management

Checked against the real src/services/marketplace/schema.sql (#333) -- the
original version of this file asserted a `marketplace_plugin_ai_tools` table,
`is_enabled`/`requires_configuration` columns, and inserted into
marketplace_ai_tools_configurations/marketplace_ai_tools_registrations with
columns neither table has (e.g. plugin_id/tool_name/installation_id on
registrations, which only has ai_tool_id/service_name/endpoint_url/status) --
none of that exists in the real schema.
"""

import json
import os
import uuid

import asyncpg
import pytest

pytestmark = [pytest.mark.integration]


async def get_db_connection():
    """Real test-DB connection, matching what marketplace's own Settings
    resolves to (env-driven, see tests/integration/conftest.py)."""
    return await asyncpg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )


@pytest.mark.asyncio
async def test_ai_tools_enhanced_schema(marketplace_schema_ready):
    """Test that AI tools tables + enhanced columns exist"""
    conn = await get_db_connection()

    try:
        # Check AI tools tables exist
        tables = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND (table_name LIKE 'marketplace_ai%' OR table_name LIKE '%ai%')
            ORDER BY table_name
        """
        )

        table_names = [row["table_name"] for row in tables]

        assert "marketplace_ai_tools" in table_names
        assert "marketplace_ai_tools_configurations" in table_names
        assert "marketplace_ai_tools_registrations" in table_names

        # Check enhanced columns in marketplace_ai_tools
        columns = await conn.fetch(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'marketplace_ai_tools'
            ORDER BY column_name
        """
        )

        column_names = [row["column_name"] for row in columns]

        # Enhanced columns (real schema uses "active", not "is_enabled";
        # there is no "requires_configuration" column at all)
        assert "configuration_schema" in column_names
        assert "default_configuration" in column_names
        assert "active" in column_names
        assert "required_tier" in column_names
        assert "category" in column_names
        assert "tags" in column_names
        assert "allow_user_configuration" in column_names

        # Check indexes
        indexes = await conn.fetch(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND (indexname LIKE 'ai_%' OR indexname LIKE '%ai%')
            ORDER BY indexname
        """
        )

        index_names = [row["indexname"] for row in indexes]
        assert len(index_names) > 0

        print("✅ AI tools schema validated successfully")
        print(f"   - Tables found: {len(table_names)}")
        print(f"   - Enhanced columns: {len(column_names)}")
        print(f"   - Indexes created: {len(index_names)}")

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_ai_tools_configuration_table(marketplace_schema_ready):
    """Test AI tools configuration table structure -- a per-user
    configuration row references a real marketplace_ai_tools row via
    ai_tool_id (the real FK; the table has no plugin_id/tool_name of its own)."""
    conn = await get_db_connection()

    try:
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
        plugin_id = plugin_result["id"]

        ai_tool_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_ai_tools (plugin_id, tool_name, display_name)
            VALUES ($1, $2, $3)
            RETURNING id
        """,
            plugin_id,
            "test_tool",
            "Test Tool",
        )
        ai_tool_id = ai_tool_result["id"]

        # "admin" is schema.sql's own seeded default user -- a real,
        # already-existing user_id for the configurations row's FK.
        result = await conn.fetchrow(
            """
            INSERT INTO marketplace_ai_tools_configurations
            (user_id, ai_tool_id, configuration)
            VALUES ($1, $2, $3)
            RETURNING id, ai_tool_id, configuration
        """,
            "admin",
            ai_tool_id,
            json.dumps({"api_key": "default_key"}),
        )

        assert result["ai_tool_id"] == ai_tool_id

        config = json.loads(result["configuration"])
        assert config["api_key"] == "default_key"

        # Clean up
        await conn.execute(
            "DELETE FROM marketplace_ai_tools_configurations WHERE ai_tool_id = $1",
            ai_tool_id,
        )
        await conn.execute("DELETE FROM marketplace_ai_tools WHERE id = $1", ai_tool_id)
        await conn.execute("DELETE FROM marketplace_plugins WHERE id = $1", plugin_id)

    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_ai_tools_registrations_round_trip(marketplace_schema_ready):
    """The real schema has no enum CHECK constraint on
    marketplace_ai_tools_registrations.status (a plain VARCHAR DEFAULT
    'active') -- this verifies a real insert/query/cleanup round trip against
    the table's actual columns (ai_tool_id/service_name/endpoint_url/status)
    instead of a fictional constraint."""
    conn = await get_db_connection()

    try:
        plugin_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_plugins
            (name, display_name, description, author, author_email)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
        """,
            f"test_plugin_reg_{uuid.uuid4().hex[:8]}",
            "Test Plugin Registrations",
            "A test plugin",
            "Test Author",
            "test@example.com",
        )
        plugin_id = plugin_result["id"]

        ai_tool_result = await conn.fetchrow(
            """
            INSERT INTO marketplace_ai_tools (plugin_id, tool_name, display_name)
            VALUES ($1, $2, $3)
            RETURNING id
        """,
            plugin_id,
            "test_tool_reg",
            "Test Tool Reg",
        )
        ai_tool_id = ai_tool_result["id"]

        statuses = ["pending", "active", "inactive", "error"]
        for status in statuses:
            await conn.execute(
                """
                INSERT INTO marketplace_ai_tools_registrations
                (ai_tool_id, service_name, endpoint_url, status)
                VALUES ($1, $2, $3, $4)
            """,
                ai_tool_id,
                f"svc-{status}",
                f"http://svc-{status}/health",
                status,
            )

        rows = await conn.fetch(
            "SELECT status FROM marketplace_ai_tools_registrations WHERE ai_tool_id = $1",
            ai_tool_id,
        )
        assert {row["status"] for row in rows} == set(statuses)

        # Clean up
        await conn.execute(
            "DELETE FROM marketplace_ai_tools_registrations WHERE ai_tool_id = $1",
            ai_tool_id,
        )
        await conn.execute("DELETE FROM marketplace_ai_tools WHERE id = $1", ai_tool_id)
        await conn.execute("DELETE FROM marketplace_plugins WHERE id = $1", plugin_id)

        print("✅ AI tools registrations round trip validated successfully")

    finally:
        await conn.close()
