"""Regression tests: concurrent first-callers must create exactly one DB pool.

plugin-registry's ``get_postgres_connection()`` and plugin-state-manager's
``get_db_pool()`` both lazily create a module-global asyncpg pool on first call. Before
this fix, neither guarded that lazy creation with a lock: two coroutines racing to be
the first caller (e.g. two concurrent request handlers at startup) could both observe
the global as unset, both call ``create_pg_pool(...)``, and the second assignment would
silently win — leaking the first pool's connections forever and, since
plugin-state-manager also sets ``auto_create=True``, risking a duplicate ``CREATE
DATABASE`` race. marketplace and rag-pipeline already had the correct double-checked-lock
pattern (this test's shape mirrors how their behaviour would be proven); these two
services didn't.

Loaded via sys.path + a stale-cache clear (matches
test_plugin_registry_webhook_persistence.py's established pattern) since each service's
``core.database`` transitively imports its own ``config``/``core.state``, and
conftest.py's session-scoped service loader already cached different services' bare
``core``/``config`` names first.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SRC_SERVICES = Path(__file__).resolve().parents[2] / "src" / "services"


def _fresh_import(service_dir: str, module_path: str):
    sys.path.insert(0, str(_SRC_SERVICES / service_dir))
    for stale in list(sys.modules):
        if (
            stale == "core"
            or stale.startswith("core.")
            or stale in ("config", "models")
        ):
            del sys.modules[stale]
    import importlib

    return importlib.import_module(module_path)


class _FakePool:
    """Distinct per creation, so accidental duplicate creation is detectable by identity."""


@pytest.mark.asyncio
async def test_plugin_registry_concurrent_first_calls_create_one_pool(monkeypatch):
    database = _fresh_import("plugin-registry", "core.database")
    monkeypatch.setattr(database, "postgres_pool", None)
    # Fresh lock too -- a prior test may have left the module-level lock acquired
    # or associated with a since-closed event loop.
    monkeypatch.setattr(database, "_pool_lock", asyncio.Lock())

    calls = []

    async def _slow_create_pool(**kwargs):
        await asyncio.sleep(0.01)  # forces both callers past the fast-path check
        pool = _FakePool()
        calls.append(pool)
        return pool

    monkeypatch.setattr(
        database, "create_pg_pool", AsyncMock(side_effect=_slow_create_pool)
    )

    first, second = await asyncio.gather(
        database.get_postgres_connection(), database.get_postgres_connection()
    )

    assert len(calls) == 1, "two concurrent first-callers must not each create a pool"
    assert first is second is database.postgres_pool


@pytest.mark.asyncio
async def test_plugin_state_manager_concurrent_first_calls_create_one_pool(monkeypatch):
    database = _fresh_import("plugin-state-manager", "core.database")
    monkeypatch.setattr(database, "_pool", None)
    monkeypatch.setattr(database, "_pool_lock", asyncio.Lock())

    calls = []

    async def _slow_create_pool(**kwargs):
        await asyncio.sleep(0.01)
        pool = _FakePool()
        calls.append(pool)
        return pool

    monkeypatch.setattr(
        database, "create_pg_pool", AsyncMock(side_effect=_slow_create_pool)
    )

    first, second = await asyncio.gather(database.get_db_pool(), database.get_db_pool())

    assert len(calls) == 1, "two concurrent first-callers must not each create a pool"
    assert first is second is database._pool
