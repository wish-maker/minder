import os

import asyncpg
import pytest

pytestmark = [pytest.mark.integration]


async def get_db_connection():
    """Real test-DB connection, matching what marketplace's own Settings
    resolves to (env-driven, see tests/integration/conftest.py) -- the
    original hardcoded host=localhost/user=minder/db=minder_marketplace never
    matched CI's real postgres (user=postgres, db=minder_test) (#333)."""
    return await asyncpg.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
    )


async def test_database_schema_created(marketplace_schema_ready):
    """Test that marketplace database schema is created correctly.

    Assertions here are checked directly against the real, current
    src/services/marketplace/schema.sql (#333) -- the original version of
    this test also asserted named CHECK constraints, an updated_at trigger
    function, and a NOT NULL author/author_email, none of which exist in the
    real schema (it uses plain VARCHAR columns with no CHECK/trigger
    machinery at all).
    """
    conn = await get_db_connection()

    # Check tables exist
    tables = await conn.fetch(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """
    )

    table_names = [row["table_name"] for row in tables]

    # Core tables
    assert "marketplace_plugins" in table_names
    assert "marketplace_plugin_versions" in table_names
    assert "marketplace_plugin_tiers" in table_names
    assert "marketplace_licenses" in table_names
    assert "marketplace_installations" in table_names
    assert "marketplace_ai_tools" in table_names
    assert "marketplace_categories" in table_names
    assert "marketplace_users" in table_names

    # Check indexes
    indexes = await conn.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY indexname
    """
    )

    index_names = [row["indexname"] for row in indexes]
    assert "idx_marketplace_plugins_name" in index_names
    assert "idx_marketplace_plugins_status" in index_names
    assert "idx_marketplace_plugins_pricing_model" in index_names
    assert "idx_marketplace_licenses_user_id" in index_names
    assert "idx_marketplace_licenses_plugin_id" in index_names
    assert "idx_marketplace_installations_user_id" in index_names
    assert "idx_marketplace_ai_tools_plugin_id" in index_names

    # Check foreign keys
    fks = await conn.fetch(
        """
        SELECT
            tc.table_name,
            kcu.column_name,
            ccu.table_name AS foreign_table_name,
            ccu.column_name AS foreign_column_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY'
        ORDER BY tc.table_name
    """
    )

    # Should have foreign keys
    assert len(fks) > 0

    # Check nullability on marketplace_plugins -- name/display_name are the
    # real NOT NULL columns; author/author_email are nullable (schema.sql
    # declares them as plain `VARCHAR(255)` with no NOT NULL).
    plugins_columns = await conn.fetch(
        """
        SELECT column_name, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'marketplace_plugins'
            AND table_schema = 'public'
        ORDER BY column_name
    """
    )

    columns_dict = {row["column_name"]: row["is_nullable"] for row in plugins_columns}

    assert columns_dict.get("name") == "NO"
    assert columns_dict.get("display_name") == "NO"
    assert columns_dict.get("author") == "YES"
    assert columns_dict.get("author_email") == "YES"

    # Check CASCADE delete on user_id foreign keys (marketplace_licenses and
    # marketplace_installations both reference marketplace_users(user_id)
    # ON DELETE CASCADE)
    cascade_fks = await conn.fetch(
        """
        SELECT
            tc.table_name,
            kcu.column_name,
            rc.delete_rule
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.referential_constraints rc
            ON tc.constraint_name = rc.constraint_name
        WHERE kcu.column_name = 'user_id'
            AND rc.delete_rule = 'CASCADE'
        ORDER BY tc.table_name
    """
    )

    cascade_tables = [row["table_name"] for row in cascade_fks]

    assert "marketplace_licenses" in cascade_tables
    assert "marketplace_installations" in cascade_tables

    await conn.close()
