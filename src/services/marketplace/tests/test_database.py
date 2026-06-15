# services/marketplace/tests/test_database.py
import pytest

from services.marketplace.core.database import close_pool, get_pool


@pytest.mark.asyncio
async def test_database_pool_connection():
    """Test that database pool can be created and used"""
    pool = await get_pool()

    # Should be able to get a connection
    async with pool.acquire() as conn:
        # Simple query
        result = await conn.fetchval("SELECT 1")
        assert result == 1

        # Check tables exist
        tables = await conn.fetch("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
        """)
        table_names = [row["table_name"] for row in tables]
        assert "marketplace_plugins" in table_names

    await close_pool()


@pytest.mark.asyncio
async def test_database_pool_reuse():
    """Test that database pool is reused across calls"""
    pool1 = await get_pool()
    pool2 = await get_pool()

    # Should be the same pool instance
    assert pool1 is pool2

    await close_pool()
