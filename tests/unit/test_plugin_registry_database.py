"""Unit tests for plugin-registry's core/database.py.

save_plugin_manifest/load_all_plugin_manifests are already covered by
test_plugin_registry_webhook_persistence.py -- this covers everything else
in the module, which had almost no direct coverage: _json_list's decode
fallbacks, get_postgres_connection's cached-pool short-circuit,
create_plugins_table_if_not_exists, load_plugins_from_database,
update_plugin_in_database's column whitelist/no-op/re-raise contract,
load_plugin_config/save_plugin_config, and delete_plugin_from_database's
three-table transaction.

Same `_fresh_import` pattern as test_plugin_registry_webhook_persistence.py
(loaded via sys.path + a stale-cache clear, since core.database does
package-qualified `from core.state import ...` / `from models import ...`
imports that need the real plugin-registry package tree on sys.path).
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
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


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    """asyncpg.Pool supports .fetch()/.fetchrow()/.execute() directly (it
    acquires a connection internally) in addition to .acquire() -- delegate
    both surfaces to the same underlying fake conn, matching how
    load_plugins_from_database calls conn.fetch(...) directly on whatever
    get_postgres_connection() returns."""

    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture(autouse=True)
def _clean_plugins_db():
    database.plugins_db.clear()
    yield
    database.plugins_db.clear()


@pytest.fixture
def fake_pool(monkeypatch):
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=_FakeTransaction())
    pool = _FakePool(conn)
    monkeypatch.setattr(
        database, "get_postgres_connection", AsyncMock(return_value=pool)
    )
    return conn


# --- _json_list ---------------------------------------------------------


def test_json_list_passes_through_a_real_list():
    assert database._json_list(["a", "b"]) == ["a", "b"]


def test_json_list_decodes_a_json_string():
    assert database._json_list('["a", "b"]') == ["a", "b"]


def test_json_list_returns_empty_for_none_or_empty_string():
    assert database._json_list(None) == []
    assert database._json_list("") == []


def test_json_list_returns_empty_for_invalid_json():
    assert database._json_list("{not valid json") == []


def test_json_list_returns_empty_when_json_decodes_to_a_non_list():
    assert database._json_list('{"a": 1}') == []


# --- get_postgres_connection ---------------------------------------------


@pytest.mark.asyncio
async def test_get_postgres_connection_returns_cached_pool_without_recreating(
    monkeypatch,
):
    sentinel_pool = object()
    monkeypatch.setattr(database, "postgres_pool", sentinel_pool)
    create_pool_spy = AsyncMock()
    monkeypatch.setattr(database, "create_pg_pool", create_pool_spy)

    result = await database.get_postgres_connection()

    assert result is sentinel_pool
    create_pool_spy.assert_not_awaited()


# --- create_plugins_table_if_not_exists -----------------------------------


@pytest.mark.asyncio
async def test_create_plugins_table_if_not_exists_applies_schema(
    fake_pool, monkeypatch
):
    apply_schema_spy = AsyncMock()
    monkeypatch.setattr(database, "apply_schema", apply_schema_spy)

    await database.create_plugins_table_if_not_exists()

    apply_schema_spy.assert_awaited_once()
    args, _ = apply_schema_spy.call_args
    assert args[1] == database._SCHEMA_PATH


@pytest.mark.asyncio
async def test_create_plugins_table_if_not_exists_reraises_on_failure(
    fake_pool, monkeypatch
):
    async def boom(pool, path):
        raise ConnectionError("db unreachable")

    monkeypatch.setattr(database, "apply_schema", boom)

    with pytest.raises(ConnectionError):
        await database.create_plugins_table_if_not_exists()


# --- load_plugins_from_database --------------------------------------------


def _plugin_row(**overrides):
    from datetime import datetime, timezone

    row = {
        "name": "weather",
        "version": "1.0.0",
        "description": "Weather plugin",
        "author": "tester",
        "status": "enabled",
        "enabled": True,
        "dependencies": '["core"]',
        "capabilities": [],
        "data_sources": None,
        "databases": "not-json",
        "health_status": None,
        "last_health_check": None,
        "registered_at": datetime.now(timezone.utc),
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_load_plugins_from_database_populates_cache(fake_pool):
    fake_pool.fetch = AsyncMock(return_value=[_plugin_row()])

    await database.load_plugins_from_database()

    assert "weather" in database.plugins_db
    info = database.plugins_db["weather"]
    assert info.dependencies == ["core"]  # JSON string decoded
    assert info.databases == []  # invalid JSON falls back to []
    assert info.health_status == "unknown"  # None falls back to the default


@pytest.mark.asyncio
async def test_load_plugins_from_database_survives_a_query_failure(fake_pool):
    fake_pool.fetch = AsyncMock(side_effect=ConnectionError("db down"))

    await database.load_plugins_from_database()  # must not raise

    assert database.plugins_db == {}


# --- update_plugin_in_database ----------------------------------------------


@pytest.mark.asyncio
async def test_update_plugin_in_database_filters_to_allowed_columns(fake_pool):
    await database.update_plugin_in_database(
        "weather", status="enabled", not_a_real_column="ignored"
    )

    fake_pool.execute.assert_awaited_once()
    query, *params = fake_pool.execute.call_args.args
    assert "not_a_real_column" not in query
    assert params == ["weather", "enabled"]


@pytest.mark.asyncio
async def test_update_plugin_in_database_noop_when_nothing_valid_to_update(
    fake_pool,
):
    await database.update_plugin_in_database("weather", not_a_real_column="ignored")

    fake_pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_plugin_in_database_allows_stable_id_and_marketplace_plugin_id(
    fake_pool,
):
    """#747: both new columns must be settable through the same upsert path
    every other plugin field already goes through."""
    await database.update_plugin_in_database(
        "weather", stable_id="abc-123", marketplace_plugin_id="mkt-uuid-1"
    )

    fake_pool.execute.assert_awaited_once()
    query, *params = fake_pool.execute.call_args.args
    assert "stable_id" in query
    assert "marketplace_plugin_id" in query
    assert params == ["weather", "abc-123", "mkt-uuid-1"]


@pytest.mark.asyncio
async def test_update_plugin_in_database_reraises_on_failure(fake_pool):
    fake_pool.execute = AsyncMock(side_effect=ConnectionError("db down"))

    with pytest.raises(ConnectionError):
        await database.update_plugin_in_database("weather", status="enabled")


# --- find_plugin_name_by_stable_id / rename_plugin_row / -------------------
# --- get_marketplace_plugin_id (#747) ---------------------------------------


@pytest.mark.asyncio
async def test_find_plugin_name_by_stable_id_returns_the_current_name(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value={"name": "weather"})

    result = await database.find_plugin_name_by_stable_id("some-stable-id")

    assert result == "weather"
    args, _ = fake_pool.fetchrow.call_args
    assert "stable_id" in args[0]
    assert args[1] == "some-stable-id"


@pytest.mark.asyncio
async def test_find_plugin_name_by_stable_id_returns_none_when_no_row(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value=None)

    result = await database.find_plugin_name_by_stable_id("unknown-stable-id")

    assert result is None


@pytest.mark.asyncio
async def test_find_plugin_name_by_stable_id_short_circuits_on_falsy_input(
    fake_pool,
):
    result = await database.find_plugin_name_by_stable_id("")

    assert result is None
    fake_pool.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_rename_plugin_row_updates_name_in_place(fake_pool):
    await database.rename_plugin_row("old_name", "new_name")

    fake_pool.execute.assert_awaited_once()
    query, *params = fake_pool.execute.call_args.args
    assert "UPDATE plugins SET name" in query
    assert params == ["new_name", "old_name"]


@pytest.mark.asyncio
async def test_rename_plugin_row_is_a_noop_when_names_match(fake_pool):
    await database.rename_plugin_row("same_name", "same_name")

    fake_pool.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_marketplace_plugin_id_returns_the_persisted_value(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value={"marketplace_plugin_id": "mkt-uuid-1"})

    result = await database.get_marketplace_plugin_id("weather")

    assert result == "mkt-uuid-1"


@pytest.mark.asyncio
async def test_get_marketplace_plugin_id_returns_none_when_no_row(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value=None)

    result = await database.get_marketplace_plugin_id("weather")

    assert result is None


# --- load_plugin_config / save_plugin_config --------------------------------


@pytest.mark.asyncio
async def test_load_plugin_config_parses_json_string_config(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value={"config": '{"threshold": 5}'})

    result = await database.load_plugin_config("weather")

    assert result == {"threshold": 5}


@pytest.mark.asyncio
async def test_load_plugin_config_passes_through_dict_config(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value={"config": {"threshold": 5}})

    result = await database.load_plugin_config("weather")

    assert result == {"threshold": 5}


@pytest.mark.asyncio
async def test_load_plugin_config_returns_empty_when_no_row(fake_pool):
    fake_pool.fetchrow = AsyncMock(return_value=None)

    result = await database.load_plugin_config("weather")

    assert result == {}


@pytest.mark.asyncio
async def test_load_plugin_config_returns_empty_and_swallows_errors(fake_pool):
    fake_pool.fetchrow = AsyncMock(side_effect=ConnectionError("db down"))

    result = await database.load_plugin_config("weather")  # must not raise

    assert result == {}


@pytest.mark.asyncio
async def test_save_plugin_config_upserts_serialized_json(fake_pool):
    await database.save_plugin_config("weather", {"threshold": 5})

    fake_pool.execute.assert_awaited_once()
    args, _ = fake_pool.execute.call_args
    assert args[1] == "weather"
    assert args[2] == '{"threshold": 5}'


# --- delete_plugin_from_database ---------------------------------------------


@pytest.mark.asyncio
async def test_delete_plugin_from_database_deletes_all_three_tables(fake_pool):
    await database.delete_plugin_from_database("weather")

    assert fake_pool.execute.await_count == 3
    tables_touched = [call.args[0] for call in fake_pool.execute.call_args_list]
    assert any("FROM plugins " in q for q in tables_touched)
    assert any("FROM plugin_manifests" in q for q in tables_touched)
    assert any("FROM plugin_configs" in q for q in tables_touched)


@pytest.mark.asyncio
async def test_delete_plugin_from_database_reraises_on_failure(fake_pool):
    fake_pool.execute = AsyncMock(side_effect=ConnectionError("db down"))

    with pytest.raises(ConnectionError):
        await database.delete_plugin_from_database("weather")
