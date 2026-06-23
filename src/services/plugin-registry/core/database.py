"""
Core Database Module

Manages PostgreSQL connection pool and connection lifecycle.
"""

import logging
from contextlib import asynccontextmanager

import asyncpg

from config import settings

logger = logging.getLogger(__name__)

# Global connection pool
connection_pool = None


@asynccontextmanager
async def get_postgres_connection():
    """
    Get PostgreSQL connection from pool

    Yields:
        asyncpg.Connection: Database connection

    Example:
        >>> async with get_postgres_connection() as conn:
        ...     result = await conn.fetch("SELECT NOW()")
    """
    global connection_pool

    if connection_pool is None:
        raise RuntimeError("Connection pool not initialized")

    async with connection_pool.acquire() as connection:
        yield connection


async def close_postgres_connection():
    """Close PostgreSQL connection pool"""
    global connection_pool

    if connection_pool:
        await connection_pool.close()
        connection_pool = None
        logger.info("PostgreSQL connection pool closed")


async def initialize_connection_pool():
    """Initialize PostgreSQL connection pool"""
    global connection_pool

    if connection_pool is not None:
        return

    try:
        connection_pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            database=settings.POSTGRES_DB,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            min_size=5,
            max_size=20,
        )
        logger.info(
            f"✅ PostgreSQL connection pool initialized: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}"
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize connection pool: {e}")
        raise
