"""Shared asyncpg pool construction with optional database auto-creation.

Extracts the ``create_pool`` + ``InvalidCatalogNameError`` → ``CREATE DATABASE`` →
retry block that marketplace and plugin-state-manager hand-rolled near-verbatim
(issue #49). Callers pass explicit connection params — each service keeps its own
settings/env source, so NO env-var convention is imposed here and behaviour is
identical to the previous inline implementations.
"""

import logging
import re
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# Every current caller passes a trusted, service-config-derived name (#49's own
# callers: marketplace/plugin-state-manager's settings.DB_NAME), so this isn't
# attacker-reachable today -- but create_pg_pool is a SHARED helper with no
# documented constraint on `database`, and CREATE DATABASE below is unparameterized
# DDL (asyncpg has no placeholder for identifiers). Found in a background audit:
# validate against a strict allow-list before it ever reaches raw SQL, so a future
# caller that derives this from something less trusted doesn't inherit an injection
# primitive silently. Also rejects names that are technically legal Postgres
# identifiers but would need "quoting" (hyphens, mixed case, reserved words) --
# rather than partially support them, require the safe subset explicitly.
_SAFE_DATABASE_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
        if not _SAFE_DATABASE_NAME.match(database):
            raise ValueError(
                f"Refusing to auto-create database with unsafe name: {database!r}"
            )
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
        except asyncpg.DuplicateDatabaseError:
            # Some other process (a concurrent replica/instance, a restart racing
            # a crash-looping previous attempt) created it between our
            # InvalidCatalogNameError and this CREATE DATABASE -- an in-process
            # asyncio.Lock around get_pool() (as callers already have) only
            # protects concurrent coroutines in ONE process, not this
            # cross-process race. The database exists either way, so proceed.
            logger.info(f"Database {database} already created by another process")
        finally:
            await admin_conn.close()

        pool = await _create()
        logger.info(
            f"Database connection pool created for {database} after database creation"
        )
        return pool
