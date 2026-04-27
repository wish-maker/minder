# services/marketplace/tests/test_database_schema.py
import os

import asyncpg


async def get_db_connection():
    """Create database connection for testing"""
    return await asyncpg.connect(
        host="localhost",
        port=5432,
        user="minder",
        database="minder_marketplace",
    )


async def test_database_schema_created():
    """Test that marketplace database schema is created correctly"""
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
    assert "idx_marketplace_licenses_user_id" in index_names
    assert "idx_marketplace_installations_user_plugin" in index_names

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

    # Check CHECK constraints were added
    constraints = await conn.fetch(
        """
        SELECT
            tc.table_name,
            tc.constraint_name,
            cc.check_clause
        FROM information_schema.table_constraints tc
        JOIN information_schema.check_constraints cc
            ON tc.constraint_name = cc.constraint_name
        WHERE tc.constraint_schema = 'public'
            AND tc.constraint_type = 'CHECK'
        ORDER BY tc.table_name
    """
    )

    constraint_names = [row["constraint_name"] for row in constraints]

    # Verify enum constraints
    assert "check_role" in constraint_names
    assert "check_status" in constraint_names
    assert "check_pricing_model" in constraint_names
    assert "check_distribution_type" in constraint_names
    assert "check_price_monthly" in constraint_names
    assert "check_price_yearly" in constraint_names

    # Check NOT NULL constraints on plugins table
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

    # Author and author_email should be NOT NULL
    assert columns_dict.get("author") == "NO"
    assert columns_dict.get("author_email") == "NO"

    # Check featured plugins index exists
    featured_index = await conn.fetch(
        """
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
            AND indexname = 'idx_marketplace_plugins_featured'
    """
    )

    assert len(featured_index) > 0, "Featured plugins index should exist"

    # Check trigger function exists
    trigger_func = await conn.fetch(
        """
        SELECT proname
        FROM pg_proc
        WHERE proname = 'update_updated_at_column'
    """
    )

    assert len(trigger_func) > 0, "update_updated_at_column function should exist"

    # Check triggers exist
    triggers = await conn.fetch(
        """
        SELECT trigger_name
        FROM information_schema.triggers
        WHERE trigger_schema = 'public'
            AND trigger_name LIKE 'update_%_updated_at'
        ORDER BY trigger_name
    """
    )

    trigger_names = [row["trigger_name"] for row in triggers]

    # Should have triggers for tables with updated_at
    assert "update_marketplace_categories_updated_at" in trigger_names
    assert "update_marketplace_users_updated_at" in trigger_names
    assert "update_marketplace_plugins_updated_at" in trigger_names
    assert "update_marketplace_licenses_updated_at" in trigger_names

    # Check CASCADE delete on user_id foreign keys
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

    # Both licenses and installations should have CASCADE
    assert "marketplace_licenses" in cascade_tables
    assert "marketplace_installations" in cascade_tables

    await conn.close()
