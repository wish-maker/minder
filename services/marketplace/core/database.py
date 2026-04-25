# services/marketplace/core/database.py
import asyncio
import logging
from typing import Optional

import asyncpg

from services.marketplace.config import settings

# Global pool instance
_pool: Optional[asyncpg.Pool] = None
_pool_lock = asyncio.Lock()

# Configure logging
logger = logging.getLogger("minder.marketplace.database")


async def get_pool() -> asyncpg.Pool:
    """Get or create database connection pool

    Returns:
        asyncpg.Pool: The database connection pool

    Raises:
        RuntimeError: If pool creation fails
    """
    global _pool

    # Fast path - return existing pool
    if _pool is not None:
        return _pool

    # Use lock to prevent concurrent pool creation
    async with _pool_lock:
        # Double-check after acquiring lock
        if _pool is not None:
            logger.debug("Reusing existing database connection pool")
            return _pool

        try:
            logger.info(
                f"Creating database connection pool: "
                f"host={settings.MARKETPLACE_DATABASE_HOST}, "
                f"port={settings.MARKETPLACE_DATABASE_PORT}, "
                f"database={settings.MARKETPLACE_DATABASE_NAME}"
            )

            _pool = await asyncpg.create_pool(
                host=settings.MARKETPLACE_DATABASE_HOST,
                port=settings.MARKETPLACE_DATABASE_PORT,
                user=settings.MARKETPLACE_DATABASE_USER,
                password=settings.MARKETPLACE_DATABASE_PASSWORD,
                database=settings.MARKETPLACE_DATABASE_NAME,
                min_size=2,
                max_size=10,
                command_timeout=60,
            )

            logger.info("Database connection pool created successfully (min_size=2, max_size=10)")

        except Exception as e:
            logger.error(f"Failed to create database connection pool: {e}")
            raise RuntimeError(f"Failed to connect to database: {e}") from e

    return _pool


async def close_pool():
    """Close database connection pool and cleanup resources"""
    global _pool

    if _pool is not None:
        logger.info("Closing database connection pool")
        try:
            await _pool.close()
            _pool = None
            logger.info("Database connection pool closed successfully")
        except Exception as e:
            logger.error(f"Error closing database connection pool: {e}")
            raise


async def get_connection():
    """Get a database connection from the pool

    Returns:
        asyncpg.connection.Connection: An async context manager for the connection

    Example:
        async with await get_connection() as conn:
            await conn.fetchval("SELECT 1")

    Raises:
        RuntimeError: If pool creation fails
    """
    try:
        pool = await get_pool()
        logger.debug("Acquiring database connection from pool")
        # Return the async context manager for connection acquisition
        return pool.acquire()
    except Exception as e:
        logger.error(f"Failed to acquire database connection: {e}")
        raise
