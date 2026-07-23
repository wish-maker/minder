"""Shared asyncpg pool construction with optional database auto-creation.

Extracts the ``create_pool`` + ``InvalidCatalogNameError`` → ``CREATE DATABASE`` →
retry block that marketplace and plugin-state-manager hand-rolled near-verbatim
(issue #49). Callers pass explicit connection params — each service keeps its own
settings/env source, so NO env-var convention is imposed here and behaviour is
identical to the previous inline implementations.
"""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


async def create_pg_pool(
    *,
    host: str,
    port: int,
    user: str,
    password: str,
    database: str,
    min_size: int = 2,
    max_size: int = 10,
    command_timeout: Optional[int] = 60,
    auto_create: bool = False,
) -> asyncpg.Pool:
    """Create an asyncpg connection pool.

    If ``auto_create`` is True and the target database doesn't exist yet
    (``InvalidCatalogNameError``), connect to the ``postgres`` maintenance database,
    ``CREATE DATABASE``, then create the pool. With ``auto_create=False`` the missing
    database error propagates unchanged.

    Args:
        host/port/user/password/database: connection parameters.
        min_size/max_size/command_timeout: pool tuning (asyncpg defaults preserved).
        auto_create: create the database on first connect if it's missing.

    Returns:
        A ready asyncpg.Pool connected to ``database``.
    """

    async def _create() -> asyncpg.Pool:
        return await asyncpg.create_pool(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )

    try:
        pool = await _create()
        logger.info(
            f"Database connection pool created for {database} "
            f"(min_size={min_size}, max_size={max_size})"
        )
        return pool
    except asyncpg.InvalidCatalogNameError:
        if not auto_create:
            raise
        logger.warning(f"Database {database} does not exist, creating...")

        admin_conn = await asyncpg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database="postgres",
        )
        try:
            await admin_conn.execute(f"CREATE DATABASE {database}")
            logger.info(f"✅ Database {database} created")
        finally:
            await admin_conn.close()

        pool = await _create()
        logger.info(
            f"Database connection pool created for {database} after database creation"
        )
        return pool
