# services/marketplace/tests/test_database_schema.py
import asyncpg

async def test_database_schema_created():
    """Test that marketplace database schema is created correctly"""
    conn = await asyncpg.connect(
        host="localhost",
        port=5432,
        user="minder",
        password="dev_password_change_me",  # nosec: B106 - Test code using dev credentials
        database="minder_marketplace"
    )

    # Check tables exist
    tables = await conn.fetch("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name
    """)

    table_names = [row['table_name'] for row in tables]

    # Core tables
    assert 'marketplace_plugins' in table_names
    assert 'marketplace_plugin_versions' in table_names
    assert 'marketplace_plugin_tiers' in table_names
    assert 'marketplace_licenses' in table_names
    assert 'marketplace_installations' in table_names
    assert 'marketplace_ai_tools' in table_names
    assert 'marketplace_categories' in table_names
    assert 'marketplace_users' in table_names

    # Check indexes
    indexes = await conn.fetch("""
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
        ORDER BY indexname
    """)

    index_names = [row['indexname'] for row in indexes]
    assert 'idx_marketplace_plugins_name' in index_names
    assert 'idx_marketplace_licenses_user_id' in index_names
    assert 'idx_marketplace_installations_user_plugin' in index_names

    # Check foreign keys
    fks = await conn.fetch("""
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
    """)

    # Should have foreign keys
    assert len(fks) > 0

    await conn.close()
