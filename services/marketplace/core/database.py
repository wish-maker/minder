# services/marketplace/core/database.py
from typing import Optional

import asyncpg

from services.marketplace.config import settings

# Global pool instance
_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create database connection pool"""
    global _pool

    if _pool is None:
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

    return _pool


async def close_pool():
    """Close database connection pool"""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None


async def get_connection():
    """Get a database connection from the pool"""
    pool = await get_pool()
    return pool.acquire()
