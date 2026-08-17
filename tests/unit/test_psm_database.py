"""Unit tests for plugin-state-manager's core/database.py.

get_db_pool's cached-pool short-circuit is exercised indirectly by other test
files (they monkeypatch it away), but the module's own logic -- get_db_config,
the actual pool-creation call to shared.db.pool.create_pg_pool,
close_db_pool, and initialize_database -- had no direct coverage.

Same `_fresh_import` pattern as test_plugin_registry_database.py (loaded via
sys.path + a stale-cache clear, since core.database does a package-qualified
`from config import settings` import that needs the real plugin-state-manager
package tree on sys.path).
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"
)


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    for stale in list(sys.modules):
        if (
            stale == "core"
            or stale.startswith("core.")
            or stale in ("config", "models")
        ):
            del sys.modules[stale]
    import importlib

    return importlib.import_module(module_path)


database = _fresh_import("core.database")


@pytest.fixture(autouse=True)
def _reset_pool():
    database._pool = None
    yield
    database._pool = None


def test_get_db_config_reads_from_settings(monkeypatch):
    monkeypatch.setattr(database.settings, "DB_HOST", "db-host", raising=False)
    monkeypatch.setattr(database.settings, "DB_PORT", 5432, raising=False)
    monkeypatch.setattr(database.settings, "DB_USER", "user1", raising=False)
    monkeypatch.setattr(database.settings, "DB_PASSWORD", "secret", raising=False)
    monkeypatch.setattr(database.settings, "DB_NAME", "psm_db", raising=False)

    config = database.get_db_config()

    assert config == {
        "host": "db-host",
        "port": 5432,
        "user": "user1",
        "password": "secret",
        "database": "psm_db",
    }


@pytest.mark.asyncio
async def test_get_db_pool_creates_once_and_reuses(monkeypatch):
    sentinel_pool = object()
    create_pool_spy = AsyncMock(return_value=sentinel_pool)
    monkeypatch.setattr(database, "create_pg_pool", create_pool_spy)

    first = await database.get_db_pool()
    second = await database.get_db_pool()

    assert first is sentinel_pool
    assert second is sentinel_pool
    create_pool_spy.assert_awaited_once()  # only created once, reused on 2nd call


@pytest.mark.asyncio
async def test_get_db_pool_passes_config_and_auto_create(monkeypatch):
    captured = {}

    async def fake_create_pg_pool(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_pg_pool", fake_create_pg_pool)
    monkeypatch.setattr(database.settings, "DB_HOST", "db-host", raising=False)
    monkeypatch.setattr(database.settings, "DB_NAME", "psm_db", raising=False)

    await database.get_db_pool()

    assert captured["host"] == "db-host"
    assert captured["database"] == "psm_db"
    assert captured["auto_create"] is True
    assert captured["min_size"] == 2
    assert captured["max_size"] == 10


@pytest.mark.asyncio
async def test_concurrent_first_callers_only_create_one_pool(monkeypatch):
    """The lock's inner re-check (the second `if _pool is not None`) guards
    against a second concurrent first-caller creating (and leaking) its own
    pool while waiting for the lock a slower first caller already holds."""
    sentinel_pool = object()
    call_count = {"n": 0}
    started = asyncio.Event()
    proceed = asyncio.Event()

    async def slow_create_pg_pool(**kwargs):
        call_count["n"] += 1
        started.set()
        await proceed.wait()
        return sentinel_pool

    monkeypatch.setattr(database, "create_pg_pool", slow_create_pg_pool)

    task1 = asyncio.create_task(database.get_db_pool())
    await started.wait()  # task1 is now inside the lock, mid-creation
    task2 = asyncio.create_task(database.get_db_pool())
    await asyncio.sleep(0)  # let task2 run its outer check and block on the lock
    proceed.set()

    result1 = await task1
    result2 = await task2

    assert result1 is sentinel_pool
    assert result2 is sentinel_pool
    assert call_count["n"] == 1  # task2 hit the inner re-check, not a 2nd create


@pytest.mark.asyncio
async def test_close_db_pool_closes_and_resets(monkeypatch):
    fake_pool = AsyncMock()
    database._pool = fake_pool

    await database.close_db_pool()

    fake_pool.close.assert_awaited_once()
    assert database._pool is None


@pytest.mark.asyncio
async def test_close_db_pool_is_a_noop_when_no_pool_exists():
    database._pool = None

    await database.close_db_pool()  # must not raise

    assert database._pool is None


@pytest.mark.asyncio
async def test_initialize_database_applies_schema(monkeypatch):
    sentinel_pool = object()
    monkeypatch.setattr(
        database, "create_pg_pool", AsyncMock(return_value=sentinel_pool)
    )
    apply_schema_spy = AsyncMock()
    monkeypatch.setattr(database, "apply_schema", apply_schema_spy)

    await database.initialize_database()

    apply_schema_spy.assert_awaited_once()
    args, _ = apply_schema_spy.call_args
    assert args[0] is sentinel_pool
    assert args[1] == database._SCHEMA_PATH
