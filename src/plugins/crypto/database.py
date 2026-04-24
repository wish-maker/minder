"""
Database connection management for Crypto Plugin
"""

import logging
import os
from contextlib import asynccontextmanager

import asyncpg

logger = logging.getLogger(__name__)

# Database connection pool
_pool: asyncpg.Pool = None


async def init_db():
    """Initialize database connection pool"""
    global _pool

    db_config = {
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "database": os.getenv("POSTGRES_DB", "minder"),
        "user": os.getenv("POSTGRES_USER", "minder"),
        "password": os.getenv("POSTGRES_PASSWORD", ""),
        "min_size": 2,
        "max_size": 10,
    }

    try:
        _pool = await asyncpg.create_pool(
            host=db_config["host"],
            port=db_config["port"],
            database=db_config["database"],
            user=db_config["user"],
            password=db_config["password"],
            min_size=db_config["min_size"],
            max_size=db_config["max_size"],
        )
        logger.info("✅ Database pool initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize database pool: {e}")
        raise


@asynccontextmanager
async def get_db():
    """Get database connection from pool"""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")

    async with _pool.acquire() as connection:
        yield connection


async def close_db():
    """Close database connection pool"""
    global _pool

    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Database pool closed")
