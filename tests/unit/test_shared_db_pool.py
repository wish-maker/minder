"""Unit tests for shared/db/pool.py's create_pg_pool auto-create path.

Found in a background audit: the CREATE DATABASE step had no handling for
asyncpg.DuplicateDatabaseError. Every caller that hits InvalidCatalogNameError
independently connects to the `postgres` maintenance DB and runs CREATE
DATABASE -- if two instances/processes of the same service race (a container
restart racing a crash-looping previous attempt, docker compose --scale,
etc.), the loser gets DuplicateDatabaseError, which used to propagate and
kill that process's startup instead of falling through to just opening the
now-existing database's pool. An in-process asyncio.Lock (which callers like
plugin-state-manager's get_db_pool already have, see
test_db_pool_race_condition.py) only protects concurrent coroutines in ONE
process -- it does nothing for this cross-process race.

No real Postgres needed: asyncpg.connect/create_pool are monkeypatched.
"""

from unittest.mock import AsyncMock

import asyncpg
import pytest

from shared.db import pool as db_pool


class _FakePool:
    pass


@pytest.mark.asyncio
async def test_auto_create_creates_database_when_missing(monkeypatch):
    create_pool_calls = []

    async def fake_create_pool(**kwargs):
        create_pool_calls.append(kwargs)
        if len(create_pool_calls) == 1:
            raise asyncpg.InvalidCatalogNameError("database does not exist")
        return _FakePool()

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

    admin_conn = AsyncMock()
    monkeypatch.setattr(asyncpg, "connect", AsyncMock(return_value=admin_conn))

    result = await db_pool.create_pg_pool(
        host="db",
        port=5432,
        user="u",
        password="p",
        database="minder",
        auto_create=True,
    )

    assert isinstance(result, _FakePool)
    admin_conn.execute.assert_awaited_once_with("CREATE DATABASE minder")
    admin_conn.close.assert_awaited_once()
    assert len(create_pool_calls) == 2  # first failed, second (post-create) succeeded


@pytest.mark.asyncio
async def test_auto_create_survives_concurrent_create_database(monkeypatch):
    """Regression guard: a DuplicateDatabaseError from CREATE DATABASE (some
    other process won the race) must not propagate -- the database exists
    either way, so this should proceed to open the pool."""

    async def fake_create_pool(**kwargs):
        raise asyncpg.InvalidCatalogNameError("database does not exist")

    call_count = {"n": 0}

    async def fake_create_pool_then_succeed(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise asyncpg.InvalidCatalogNameError("database does not exist")
        return _FakePool()

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool_then_succeed)

    admin_conn = AsyncMock()
    admin_conn.execute = AsyncMock(
        side_effect=asyncpg.DuplicateDatabaseError("database already exists")
    )
    monkeypatch.setattr(asyncpg, "connect", AsyncMock(return_value=admin_conn))

    result = await db_pool.create_pg_pool(
        host="db",
        port=5432,
        user="u",
        password="p",
        database="minder",
        auto_create=True,
    )

    assert isinstance(result, _FakePool)
    admin_conn.close.assert_awaited_once()  # cleaned up even though execute raised


@pytest.mark.asyncio
async def test_missing_database_propagates_without_auto_create(monkeypatch):
    async def fake_create_pool(**kwargs):
        raise asyncpg.InvalidCatalogNameError("database does not exist")

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

    with pytest.raises(asyncpg.InvalidCatalogNameError):
        await db_pool.create_pg_pool(
            host="db",
            port=5432,
            user="u",
            password="p",
            database="minder",
            auto_create=False,
        )
