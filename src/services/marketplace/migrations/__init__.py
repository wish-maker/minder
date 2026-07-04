"""
Marketplace Database Migrations
Idempotent schema initialization following rag-pipeline pattern
"""

import logging
import pathlib

logger = logging.getLogger(__name__)


async def run_migrations(pool):
    """
    Run database migrations (idempotent)

    This function is called on startup to ensure the database schema exists.
    It uses IF NOT EXISTS to make migrations safe to run multiple times.

    Args:
        pool: asyncpg.Pool connection pool
    """
    try:
        # Canonical, git-tracked schema (single source of truth; see #10).
        # Lives at src/services/marketplace/schema.sql — one level up from this package.
        schema_path = pathlib.Path(__file__).parent.parent / "schema.sql"

        schema_sql = schema_path.read_text()

        async with pool.acquire() as conn:
            await conn.execute(schema_sql)

        logger.info("✅ Marketplace database schema initialized successfully")

    except Exception as e:
        logger.error(f"❌ Failed to initialize marketplace schema: {e}")
        raise
