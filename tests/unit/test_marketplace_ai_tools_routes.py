"""Unit tests for marketplace's AI-tools routes (routes/ai_tools.py).

Found in a background audit: GET /v1/marketplace/ai/tools accepted no
tool_name filter, but its real consumer -- plugin-state-manager's
validate_tool_access -- calls it with params={"tool_name": tool_name}
expecting exactly that. FastAPI silently drops an unrecognized query param,
so the call always returned page one of ALL active tools, and the caller's
`tools[0]` picked up an arbitrary tool instead of the one actually being
invoked -- checking its required_tier instead of the real tool's.

GET /v1/marketplace/ai/tools/{tool_name} also had no `active` filter (unlike
its list-endpoint siblings) and no deterministic ordering, even though
tool_name is unique only per-plugin (schema.sql: UNIQUE(plugin_id,
tool_name)), not globally -- a same-name collision across two plugins could
resolve to a different plugin's tool on every query.

No real Postgres: get_pool()/pool.acquire()/conn.fetch()/fetchval() are
faked, capturing the query string + params each call receives. Isolated
import matches test_marketplace_error_handling.py's own precedent (avoids
the shared core/routes/models/config module-name collision across the
one-process pytest run).
"""

import sys
from pathlib import Path

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


(ai_tools,) = _isolated_import("routes.ai_tools")


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


@pytest.mark.asyncio
async def test_list_all_ai_tools_filters_by_tool_name_when_given(monkeypatch):
    conn = _FakeConn(count_result=1, fetch_result=[])
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    # Calling a FastAPI route function directly bypasses Query() resolution --
    # its declared defaults are the Query(...) sentinel objects themselves
    # (always truthy), not the real None/True they resolve to over HTTP. Pass
    # every param explicitly as a real Python value to avoid that trap.
    await ai_tools.list_all_ai_tools(
        active_only=True, tier=None, tool_name="get_price", limit=50, offset=0
    )

    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "at.tool_name = " in fetch_query
    assert "get_price" in fetch_params


@pytest.mark.asyncio
async def test_list_all_ai_tools_omits_tool_name_condition_when_absent(monkeypatch):
    conn = _FakeConn(count_result=0, fetch_result=[])
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    await ai_tools.list_all_ai_tools(
        active_only=True, tier=None, tool_name=None, limit=50, offset=0
    )

    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "at.tool_name = " not in fetch_query
    assert "get_price" not in fetch_params


@pytest.mark.asyncio
async def test_get_ai_tool_details_query_filters_active_and_orders_deterministically(
    monkeypatch,
):
    conn = _FakeConn(fetchrow_result=None)
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    with pytest.raises(Exception):  # 404 HTTPException -- no row found
        await ai_tools.get_ai_tool_details("some_tool")

    query, params = conn.fetchrow_calls[0]
    assert "at.active = TRUE" in query
    assert "ORDER BY p.name" in query
    assert "LIMIT 1" in query
    assert params == ("some_tool",)


async def _async_return(value):
    return value
