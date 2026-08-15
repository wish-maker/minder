"""Unit tests for marketplace's core/plugin_repository.py (#492).

list_plugins/search_plugins in routes/marketplace.py each hand-built their
own WHERE clause inline (list_plugins with a manual param_count counter
across three optional filters; search_plugins with an ILIKE search + a CASE
WHEN ranking expression), and get_featured_plugins/get_plugin each
duplicated the exact same 21-column SELECT list a further two times --
despite PLUGIN_COLUMNS already existing as the canonical list for
create_plugin/update_plugin's RETURNING clauses. Extracted into
core/plugin_repository.py, matching the same "thin routes + thick core"
convention #357/#493/#494 established for rag-pipeline.

Loaded by path (matching test_marketplace_pagination.py's own convention,
#266): conftest.py loads every service's main.py into ONE shared pytest
process, so a generic `core`/`models`/`config` module from an earlier-loaded
service can already be cached in sys.modules by the time this file
collects -- stale-clear those slots and prepend marketplace's own dir.

No real Postgres: pool.acquire()/conn.fetch()/fetchval()/fetchrow() are
faked, capturing the query string + params each call receives.
"""

import importlib.util
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

_MARKETPLACE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
)
sys.path.insert(0, str(_MARKETPLACE_DIR))
for _stale in list(sys.modules):
    if (
        _stale == "core"
        or _stale.startswith("core.")
        or _stale == "config"
        or _stale == "models"
        or _stale.startswith("models.")
    ):
        del sys.modules[_stale]

_spec = importlib.util.spec_from_file_location(
    "_marketplace_plugin_repository_under_test",
    _MARKETPLACE_DIR / "core" / "plugin_repository.py",
)
plugin_repository = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = plugin_repository
_spec.loader.exec_module(plugin_repository)


def _fake_row(**overrides):
    row = {
        "id": str(uuid.uuid4()),
        "name": "weather",
        "display_name": "Weather",
        "description": "Polls a keyless weather API.",
        "author": "Minder Team",
        "repository_url": "https://example.com/weather",
        "distribution_type": "git",
        "docker_image": None,
        "current_version": "1.0.0",
        "pricing_model": "free",
        "base_tier": "community",
        "status": "approved",
        "featured": False,
        "download_count": 0,
        "rating_average": None,
        "rating_count": 0,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "published_at": None,
        "developer_id": None,
        "category_id": None,
        "requires_services": "[]",
    }
    row.update(overrides)
    return row


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        return False


class _FakeConn:
    def __init__(self, count_result=0, fetch_result=None, fetchrow_result=None):
        self.count_result = count_result
        self.fetch_result = fetch_result or []
        self.fetchrow_result = fetchrow_result
        self.fetchval_calls = []
        self.fetch_calls = []
        self.fetchrow_calls = []

    async def fetchval(self, query, *params):
        self.fetchval_calls.append((query, params))
        return self.count_result

    async def fetch(self, query, *params):
        self.fetch_calls.append((query, params))
        return self.fetch_result

    async def fetchrow(self, query, *params):
        self.fetchrow_calls.append((query, params))
        return self.fetchrow_result


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquireCtx(self._conn)


def test_row_to_plugin_response_maps_all_fields():
    row = _fake_row(requires_services='["influxdb"]')
    result = plugin_repository.row_to_plugin_response(row)

    assert result.id == row["id"]
    assert result.name == "weather"
    assert result.requires_services == ["influxdb"]


def test_row_to_plugin_response_defaults_missing_requires_services_to_empty_list():
    row = _fake_row(requires_services=None)
    result = plugin_repository.row_to_plugin_response(row)
    assert result.requires_services == []


@pytest.mark.asyncio
async def test_list_plugins_page_with_no_filters_uses_1_equals_1():
    conn = _FakeConn(count_result=0, fetch_result=[])
    pool = _FakePool(conn)

    await plugin_repository.list_plugins_page(pool, None, None, None, 10, 0)

    count_query = conn.fetchval_calls[0][0]
    assert "WHERE 1=1" in count_query
    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "WHERE 1=1" in fetch_query
    assert fetch_params == (10, 0)


@pytest.mark.asyncio
async def test_list_plugins_page_builds_where_clause_for_all_three_filters():
    conn = _FakeConn(count_result=2, fetch_result=[_fake_row(), _fake_row()])
    pool = _FakePool(conn)

    plugins, total = await plugin_repository.list_plugins_page(
        pool, "approved", "monitoring", "free", 25, 5
    )

    assert total == 2
    assert len(plugins) == 2

    count_query, count_params = conn.fetchval_calls[0]
    assert "status = $1" in count_query
    assert "category_id = $2" in count_query
    assert "pricing_model = $3" in count_query
    assert count_params == ("approved", "monitoring", "free")

    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "LIMIT $4 OFFSET $5" in fetch_query
    assert fetch_params == ("approved", "monitoring", "free", 25, 5)


@pytest.mark.asyncio
async def test_search_plugins_page_wraps_query_in_wildcards_and_ranks_exact_first():
    conn = _FakeConn(count_result=1, fetch_result=[_fake_row(name="weather")])
    pool = _FakePool(conn)

    plugins, total = await plugin_repository.search_plugins_page(pool, "weather", 10, 0)

    assert total == 1
    assert plugins[0].name == "weather"

    count_query, count_params = conn.fetchval_calls[0]
    assert count_params == ("%weather%",)
    assert "status = 'approved'" in count_query

    fetch_query, fetch_params = conn.fetch_calls[0]
    # The ranking CASE must test against the BARE query ($2), not the
    # wildcarded substring pattern ($1) -- reusing $1 here meant a plugin
    # named e.g. "supernetwork" (a substring match) and one literally named
    # "network" (an exact match) both ranked 0 for q="network", so a
    # more-downloaded partial match could outrank the exact-name plugin,
    # contradicting this function's own documented "exact match first"
    # ranking (found in a background audit).
    assert "CASE WHEN name ILIKE $2 THEN 0 ELSE 1 END" in fetch_query
    assert fetch_params == ("%weather%", "weather", 10, 0)


@pytest.mark.asyncio
async def test_get_featured_plugins_filters_featured_and_approved():
    conn = _FakeConn(fetch_result=[_fake_row(featured=True)])
    pool = _FakePool(conn)

    plugins = await plugin_repository.get_featured_plugins(pool, 5)

    assert len(plugins) == 1
    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "featured = TRUE AND status = 'approved'" in fetch_query
    assert fetch_params == (5,)


@pytest.mark.asyncio
async def test_get_plugin_by_id_returns_none_when_not_found():
    conn = _FakeConn(fetchrow_result=None)
    pool = _FakePool(conn)

    result = await plugin_repository.get_plugin_by_id(pool, "does-not-exist")

    assert result is None


@pytest.mark.asyncio
async def test_get_plugin_by_id_returns_mapped_response_when_found():
    row = _fake_row()
    conn = _FakeConn(fetchrow_result=row)
    pool = _FakePool(conn)

    result = await plugin_repository.get_plugin_by_id(pool, row["id"])

    assert result is not None
    assert result.id == row["id"]
    fetchrow_query, fetchrow_params = conn.fetchrow_calls[0]
    assert fetchrow_params == (row["id"],)
