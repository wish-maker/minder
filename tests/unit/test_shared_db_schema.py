"""Unit tests for shared/db/schema.py's apply_schema (issue #17).

Standardizes how services initialize their DB schema from a git-tracked
schema.sql at startup, but had zero test coverage of its own. No real
Postgres needed: a fake pool/connection stands in for asyncpg.Pool, and a
real file on disk (tmp_path) exercises the actual path/read logic.
"""

from unittest.mock import AsyncMock

import pytest

from shared.db import schema as db_schema


class _FakeConn:
    def __init__(self):
        self.execute = AsyncMock()


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _FakeAcquire(self.conn)


@pytest.mark.asyncio
async def test_apply_schema_reads_file_and_executes_against_the_pool(tmp_path):
    sql_file = tmp_path / "schema.sql"
    sql_file.write_text(
        "CREATE TABLE IF NOT EXISTS widgets (id SERIAL PRIMARY KEY);", encoding="utf-8"
    )
    pool = _FakePool()

    await db_schema.apply_schema(pool, sql_file)

    pool.conn.execute.assert_awaited_once_with(
        "CREATE TABLE IF NOT EXISTS widgets (id SERIAL PRIMARY KEY);"
    )


@pytest.mark.asyncio
async def test_apply_schema_accepts_a_string_path(tmp_path):
    sql_file = tmp_path / "schema.sql"
    sql_file.write_text(
        "CREATE INDEX IF NOT EXISTS idx_x ON widgets(id);", encoding="utf-8"
    )
    pool = _FakePool()

    await db_schema.apply_schema(pool, str(sql_file))

    pool.conn.execute.assert_awaited_once_with(
        "CREATE INDEX IF NOT EXISTS idx_x ON widgets(id);"
    )


@pytest.mark.asyncio
async def test_apply_schema_runs_multi_statement_files_in_one_execute(tmp_path):
    sql_file = tmp_path / "schema.sql"
    multi_statement_sql = (
        "CREATE TABLE IF NOT EXISTS a (id SERIAL PRIMARY KEY);\n"
        "CREATE TABLE IF NOT EXISTS b (id SERIAL PRIMARY KEY);\n"
    )
    sql_file.write_text(multi_statement_sql, encoding="utf-8")
    pool = _FakePool()

    await db_schema.apply_schema(pool, sql_file)

    # Single execute() call carries BOTH statements -- asyncpg's simple-query
    # protocol (no bound args) runs semicolon-separated statements together.
    pool.conn.execute.assert_awaited_once_with(multi_statement_sql)


@pytest.mark.asyncio
async def test_apply_schema_propagates_a_missing_file(tmp_path):
    missing_path = tmp_path / "does-not-exist.sql"
    pool = _FakePool()

    with pytest.raises(FileNotFoundError):
        await db_schema.apply_schema(pool, missing_path)

    pool.conn.execute.assert_not_awaited()
