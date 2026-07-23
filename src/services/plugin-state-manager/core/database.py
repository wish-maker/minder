# services/plugin-state-manager/core/database.py
"""
Database connection pool management
"""

import logging
import pathlib
import sys
from typing import Optional

import asyncpg

from config import settings

# Shared pool factory owns the create_pool + auto-create-DB boilerplate (#49).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.db.pool import create_pg_pool  # noqa: E402
from shared.db.schema import apply_schema  # noqa: E402

# Declarative schema lives at the service root (schema.sql — #17).
_SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "schema.sql"

logger = logging.getLogger(__name__)

# Global connection pool
_pool: Optional[asyncpg.Pool] = None


def get_db_config() -> dict:
    """Get database configuration from the centralized settings object."""
    return {
        "host": settings.DB_HOST,
        "port": settings.DB_PORT,
        "user": settings.DB_USER,
        "password": settings.DB_PASSWORD,
        "database": settings.DB_NAME,
    }


async def get_db_pool() -> asyncpg.Pool:
    """Get or create database connection pool

    Auto-creates the database if it doesn't exist (same pattern as marketplace)
    """
    global _pool

    if _pool is None:
        config = get_db_config()
        logger.info(f"Creating database connection pool for {config['database']}")
        _pool = await create_pg_pool(
            host=config["host"],
            port=config["port"],
            user=config["user"],
            password=config["password"],
            database=config["database"],
            min_size=2,
            max_size=10,
            command_timeout=60,
            auto_create=True,
        )

    return _pool


async def close_db_pool():
    """Close database connection pool"""
    global _pool

    if _pool:
        logger.info("Closing database connection pool")
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")


async def initialize_database():
    """Initialize database tables from schema.sql (#17)."""
    pool = await get_db_pool()
    await apply_schema(pool, _SCHEMA_PATH)
    logger.info("Database tables initialized successfully")
