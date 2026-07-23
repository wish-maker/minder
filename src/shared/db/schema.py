"""Shared schema loader — apply a service's declarative .sql schema at startup.

Standardizes how services initialize their database schema (issue #17): instead of
embedding CREATE TABLE statements in Python, each service ships a git-tracked
``schema.sql`` (discoverable single source of truth) and calls ``apply_schema`` on
startup. Statements are idempotent (``CREATE TABLE IF NOT EXISTS``), so it is safe to
run every boot. Mirrors the marketplace ``run_migrations`` pattern.
"""

import logging
import pathlib
from typing import Union

import asyncpg

logger = logging.getLogger(__name__)


async def apply_schema(pool: asyncpg.Pool, sql_path: Union[str, pathlib.Path]) -> None:
    """Read a .sql schema file and execute it against ``pool``.

    A multi-statement file runs in a single ``execute`` (asyncpg's simple-query
    protocol handles semicolon-separated statements when no args are bound), so
    CREATE TABLE / CREATE INDEX blocks apply together.
    """
    path = pathlib.Path(sql_path)
    schema_sql = path.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await conn.execute(schema_sql)
    logger.info(f"✅ Schema applied from {path.name}")
