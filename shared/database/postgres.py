import asyncpg
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


class PostgresHelper:
    """PostgreSQL database helper for services"""

    def __init__(self, dsn: str, schema: str = "public"):
        self.dsn = dsn
        self.schema = schema
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(self.dsn, min_size=5, max_size=20, command_timeout=60)
        logger.info(f"Connected to PostgreSQL, schema: {self.schema}")

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from PostgreSQL")

    async def execute(self, query: str, *args, fetch: str = "all") -> Any:
        """Execute SQL query"""
        async with self.pool.acquire() as conn:
            statement = await conn.prepare(query)
            if fetch == "one":
                return await statement.fetchrow(*args)
            elif fetch == "val":
                return await statement.fetchval(*args)
            else:
                return await statement.fetch(*args)

    async def init_schema(self):
        """Initialize service schema"""
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            logger.info(f"Schema {self.schema} initialized")
