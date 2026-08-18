"""Unit tests for marketplace's core/database.py.

Every other marketplace test file monkeypatches get_pool away entirely --
none of them exercise the module's own pool-lifecycle logic: the actual
create_pg_pool call, the double-checked-locking pattern's inner re-check,
close_pool (success + error-swallowing-vs-reraising), and get_connection.

Same `_fresh_import` pattern as test_plugin_registry_database.py /
test_psm_database.py (loaded via sys.path + a stale-cache clear, since
core.database does a package-qualified `from config import settings` import
that needs the real marketplace package tree on sys.path).
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")
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


@pytest.mark.asyncio
async def test_get_pool_creates_once_and_reuses(monkeypatch):
    sentinel_pool = object()
    create_pool_spy = AsyncMock(return_value=sentinel_pool)
    monkeypatch.setattr(database, "create_pg_pool", create_pool_spy)

    first = await database.get_pool()
    second = await database.get_pool()

    assert first is sentinel_pool
    assert second is sentinel_pool
    create_pool_spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_pool_passes_config_and_auto_create(monkeypatch):
    captured = {}

    async def fake_create_pg_pool(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(database, "create_pg_pool", fake_create_pg_pool)
    monkeypatch.setattr(database.settings, "DB_HOST", "db-host", raising=False)
    monkeypatch.setattr(database.settings, "DB_NAME", "marketplace_db", raising=False)

    await database.get_pool()

    assert captured["host"] == "db-host"
    assert captured["database"] == "marketplace_db"
    assert captured["auto_create"] is True
    assert captured["min_size"] == 2
    assert captured["max_size"] == 10


@pytest.mark.asyncio
async def test_get_pool_wraps_creation_failure_in_runtime_error(monkeypatch):
    async def boom(**kwargs):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(database, "create_pg_pool", boom)

    with pytest.raises(RuntimeError, match="Failed to connect to database"):
        await database.get_pool()

    assert database._pool is None  # must not be left in a half-set state


@pytest.mark.asyncio
async def test_concurrent_first_callers_only_create_one_pool(monkeypatch):
    """The lock's inner re-check guards against a second concurrent
    first-caller creating (and leaking) its own pool while waiting for the
    lock a slower first caller already holds."""
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

    task1 = asyncio.create_task(database.get_pool())
    await started.wait()
    task2 = asyncio.create_task(database.get_pool())
    await asyncio.sleep(0)
    proceed.set()

    result1 = await task1
    result2 = await task2

    assert result1 is sentinel_pool
    assert result2 is sentinel_pool
    assert call_count["n"] == 1


@pytest.mark.asyncio
async def test_close_pool_closes_and_resets(monkeypatch):
    fake_pool = AsyncMock()
    database._pool = fake_pool

    await database.close_pool()

    fake_pool.close.assert_awaited_once()
    assert database._pool is None


@pytest.mark.asyncio
async def test_close_pool_is_a_noop_when_no_pool_exists():
    database._pool = None

    await database.close_pool()  # must not raise

    assert database._pool is None


@pytest.mark.asyncio
async def test_close_pool_reraises_on_close_failure():
    fake_pool = AsyncMock()
    fake_pool.close.side_effect = ConnectionError("close failed")
    database._pool = fake_pool

    with pytest.raises(ConnectionError):
        await database.close_pool()


@pytest.mark.asyncio
async def test_get_connection_returns_the_pools_acquire_context(monkeypatch):
    sentinel_ctx = object()

    class _FakePool:
        def acquire(self):
            return sentinel_ctx

    monkeypatch.setattr(database, "get_pool", AsyncMock(return_value=_FakePool()))

    result = await database.get_connection()

    assert result is sentinel_ctx


@pytest.mark.asyncio
async def test_get_connection_reraises_when_pool_creation_fails(monkeypatch):
    async def boom():
        raise RuntimeError("pool creation failed")

    monkeypatch.setattr(database, "get_pool", boom)

    with pytest.raises(RuntimeError, match="pool creation failed"):
        await database.get_connection()
