"""Unit tests filling ai_tools.py's remaining coverage gaps (60%).

test_marketplace_ai_tools_routes.py already locks in list_all_ai_tools'
tool_name filter (#the plugin-state-manager consumer bug) and
get_ai_tool_details' active-filter/deterministic-ordering query shape. This
adds everything else: list_all_ai_tools' tier filter + a non-empty result
row, get_plugin_ai_tools (not-found 404 + success), get_ai_tool_details'
found-row success return, sync_ai_tools (success, importer-reported failure
-> 500, and a raised exception -> backend_http_error), and
deactivate_plugin_tools (success + a raised exception -> backend_http_error).

Same isolated-import + fake-pool pattern as the sibling suite.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

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


async def _async_return(value):
    return value


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


def _patch_lazy_importer(monkeypatch, deactivate_fn):
    """deactivate_plugin_tools does `from core.ai_tools_importer import
    deactivate_plugin_ai_tools` INSIDE its own body (not at module top), so
    monkeypatching an attribute on `ai_tools` doesn't reach it -- and by
    test-call time _isolated_import's own cleanup has already evicted every
    real 'core.*' module from sys.modules, so a fresh real import would
    either fail or (worse) silently resolve to a stale 'core' package left
    behind by a different service's test file. Sidestep real import
    machinery entirely: inject minimal fake modules directly into
    sys.modules so the route's own `from core.ai_tools_importer import ...`
    resolves to them via the import system's own sys.modules cache
    short-circuit -- monkeypatch.setitem auto-reverts after the test."""
    import types

    fake_core = types.ModuleType("core")
    fake_importer = types.ModuleType("core.ai_tools_importer")
    fake_importer.deactivate_plugin_ai_tools = deactivate_fn
    monkeypatch.setitem(sys.modules, "core", fake_core)
    monkeypatch.setitem(sys.modules, "core.ai_tools_importer", fake_importer)


def _tool_row(**overrides):
    base = {
        "id": uuid.uuid4(),
        "plugin_id": uuid.uuid4(),
        "tool_name": "get_price",
        "tool_type": "read",
        "description": "Get the current price",
        "endpoint_path": "/actions/get_price",
        "http_method": "GET",
        "parameters_schema": {"coin": "string"},
        "response_schema": {"price": "number"},
        "required_tier": "community",
        "active": True,
        "plugin_name": "crypto",
        "plugin_display_name": "Crypto",
    }
    base.update(overrides)
    return base


# --- list_all_ai_tools: tier filter + non-empty rows -----------------------------


@pytest.mark.asyncio
async def test_list_all_ai_tools_filters_by_tier_when_given(monkeypatch):
    conn = _FakeConn(count_result=0, fetch_result=[])
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    await ai_tools.list_all_ai_tools(
        active_only=True, tier="enterprise", tool_name=None, limit=50, offset=0
    )

    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "at.required_tier = " in fetch_query
    assert "enterprise" in fetch_params


@pytest.mark.asyncio
async def test_list_all_ai_tools_serializes_rows_into_tool_dicts(monkeypatch):
    row = _tool_row()
    conn = _FakeConn(count_result=1, fetch_result=[row])
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    result = await ai_tools.list_all_ai_tools(
        active_only=True, tier=None, tool_name=None, limit=50, offset=0
    )

    assert result["count"] == 1
    assert result["total"] == 1
    tool = result["tools"][0]
    assert tool["id"] == str(row["id"])
    assert tool["plugin_id"] == str(row["plugin_id"])
    assert tool["tool_name"] == "get_price"
    assert tool["required_tier"] == "community"


# --- get_plugin_ai_tools ----------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plugin_ai_tools_404_when_plugin_missing(monkeypatch):
    conn = _FakeConn(fetchrow_result=None)
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    with pytest.raises(HTTPException) as exc:
        await ai_tools.get_plugin_ai_tools(str(uuid.uuid4()))

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_plugin_ai_tools_returns_serialized_tools(monkeypatch):
    plugin_id = str(uuid.uuid4())
    plugin_row = {"id": plugin_id, "name": "crypto"}
    row = _tool_row()
    conn = _FakeConn(fetchrow_result=plugin_row, fetch_result=[row])
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    result = await ai_tools.get_plugin_ai_tools(plugin_id)

    assert result["plugin_id"] == plugin_id
    assert result["plugin_name"] == "crypto"
    assert result["count"] == 1
    assert result["tools"][0]["tool_name"] == "get_price"
    fetch_query, fetch_params = conn.fetch_calls[0]
    assert "WHERE plugin_id = $1 AND active = TRUE" in fetch_query
    assert fetch_params == (plugin_id,)


# --- get_ai_tool_details: found-row success ---------------------------------------


@pytest.mark.asyncio
async def test_get_ai_tool_details_returns_the_found_tool(monkeypatch):
    row = _tool_row(plugin_description="A crypto price plugin")
    conn = _FakeConn(fetchrow_result=row)
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    result = await ai_tools.get_ai_tool_details("get_price")

    assert result["tool_name"] == "get_price"
    assert result["plugin_description"] == "A crypto price plugin"
    assert result["required_tier"] == "community"


# --- sync_ai_tools -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_sync_ai_tools_returns_importer_result_on_success(monkeypatch):
    fake_result = {"success": True, "imported": 2}
    monkeypatch.setattr(
        ai_tools, "sync_plugin_tools", AsyncMock(return_value=fake_result)
    )
    request = ai_tools.AIToolsSyncRequest(
        plugin_name="crypto", plugin_id=str(uuid.uuid4()), manifest={}
    )

    result = await ai_tools.sync_ai_tools(request, current_user={"sub": "svc"})

    assert result == fake_result


@pytest.mark.asyncio
async def test_sync_ai_tools_treats_a_missing_success_key_as_success(monkeypatch):
    """result.get("success", True) defaults to True when the importer's result
    dict has no "success" key at all -- backward-compat with an importer that
    predates this field, per the #351 fix comment above the check. Only an
    EXPLICIT `False` must 500; a missing key must not."""
    fake_result = {"imported": 2}  # no "success" key
    monkeypatch.setattr(
        ai_tools, "sync_plugin_tools", AsyncMock(return_value=fake_result)
    )
    request = ai_tools.AIToolsSyncRequest(
        plugin_name="crypto", plugin_id=str(uuid.uuid4()), manifest={}
    )

    result = await ai_tools.sync_ai_tools(request, current_user={"sub": "svc"})

    assert result == fake_result


@pytest.mark.asyncio
async def test_sync_ai_tools_500s_when_importer_reports_failure(monkeypatch):
    fake_result = {"success": False, "error": "bad manifest"}
    monkeypatch.setattr(
        ai_tools, "sync_plugin_tools", AsyncMock(return_value=fake_result)
    )
    request = ai_tools.AIToolsSyncRequest(
        plugin_name="crypto", plugin_id=str(uuid.uuid4()), manifest={}
    )

    with pytest.raises(HTTPException) as exc:
        await ai_tools.sync_ai_tools(request, current_user={"sub": "svc"})

    assert exc.value.status_code == 500
    assert exc.value.detail == fake_result


@pytest.mark.asyncio
async def test_sync_ai_tools_masks_a_raised_exception(monkeypatch):
    async def boom(**kwargs):
        raise RuntimeError("db-password=hunter2")

    monkeypatch.setattr(ai_tools, "sync_plugin_tools", boom)
    request = ai_tools.AIToolsSyncRequest(
        plugin_name="crypto", plugin_id=str(uuid.uuid4()), manifest={}
    )

    with pytest.raises(HTTPException) as exc:
        await ai_tools.sync_ai_tools(request, current_user={"sub": "svc"})

    assert exc.value.status_code == 500
    assert "hunter2" not in str(exc.value.detail)


# --- deactivate_plugin_tools -------------------------------------------------------


@pytest.mark.asyncio
async def test_deactivate_plugin_tools_returns_importer_result(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn()
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    fake_result = {"deactivated": 3}
    _patch_lazy_importer(monkeypatch, AsyncMock(return_value=fake_result))

    result = await ai_tools.deactivate_plugin_tools(
        plugin_id, current_user={"sub": "svc"}
    )

    assert result == fake_result


@pytest.mark.asyncio
async def test_deactivate_plugin_tools_masks_a_raised_exception(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn()
    pool = _FakePool(conn)
    monkeypatch.setattr(ai_tools, "get_pool", lambda: _async_return(pool))

    async def boom(conn, plugin_id):
        raise RuntimeError("db-password=hunter2")

    _patch_lazy_importer(monkeypatch, boom)

    with pytest.raises(HTTPException) as exc:
        await ai_tools.deactivate_plugin_tools(plugin_id, current_user={"sub": "svc"})

    assert exc.value.status_code == 500
    assert "hunter2" not in str(exc.value.detail)
