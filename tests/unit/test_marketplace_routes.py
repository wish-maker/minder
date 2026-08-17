"""Unit tests for marketplace's routes/marketplace.py route handlers.

_resolve_pagination/_build_list_response (the pure helpers) are already
covered by test_marketplace_pagination.py, and create_plugin's/update_plugin's
error-leak prevention by test_marketplace_error_handling.py -- neither
exercises the actual route bodies: delegating to core.plugin_repository with
the resolved pagination, envelope assembly, 404s, the JSONB-serialization
convention for requires_services, and the empty-body 422 on update.

Same isolated-import pattern as test_marketplace_error_handling.py --
marketplace registers no module-level Prometheus metrics, so independent
fresh imports across test files are safe.
"""

import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

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


(marketplace,) = _isolated_import("routes.marketplace")


class _FakeAcquireCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakeConn:
    def __init__(self, row=None):
        self.row = row
        self.fetchrow = AsyncMock(return_value=row)


class _FakePool:
    def __init__(self, conn=None):
        self.conn = conn or _FakeConn()

    def acquire(self):
        return _FakeAcquireCtx(self.conn)


def _plugin_response_dict(id_=None, **overrides):
    """A minimal dict satisfying every required PluginResponse field --
    list_plugins/search_plugins/get_featured_plugins pass their repository
    layer's items straight into PluginListResponse(plugins=...), which
    validates each item against PluginResponse."""
    from datetime import datetime, timezone

    fields = {
        "id": id_ or str(uuid.uuid4()),
        "name": "weather",
        "display_name": "Weather",
        "description": None,
        "author": "tester",
        "author_email": None,
        "repository_url": None,
        "distribution_type": "git",
        "docker_image": None,
        "current_version": None,
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
        "requires_services": [],
    }
    fields.update(overrides)
    return fields


# --- GET /plugins (list_plugins) --------------------------------------------


@pytest.mark.asyncio
async def test_list_plugins_resolves_pagination_and_returns_envelope(monkeypatch):
    captured = {}

    async def fake_list_page(pool, status, category, pricing_model, limit, offset):
        captured.update(
            status=status,
            category=category,
            pricing_model=pricing_model,
            limit=limit,
            offset=offset,
        )
        return ([_plugin_response_dict(), _plugin_response_dict()], 12)

    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_FakePool()))
    monkeypatch.setattr(marketplace, "list_plugins_page", fake_list_page)

    result = await marketplace.list_plugins(
        limit=None,
        offset=None,
        page=2,
        page_size=5,
        category="tools",
        pricing_model="free",
        status="approved",
    )

    # page=2/page_size=5 (no explicit limit/offset) -> limit=5, offset=5.
    assert captured == {
        "status": "approved",
        "category": "tools",
        "pricing_model": "free",
        "limit": 5,
        "offset": 5,
    }
    assert result.count == 2
    assert result.total == 12
    assert result.page == 2


@pytest.mark.asyncio
async def test_list_plugins_prefers_explicit_limit_offset_over_page(monkeypatch):
    captured = {}

    async def fake_list_page(pool, status, category, pricing_model, limit, offset):
        captured["limit"] = limit
        captured["offset"] = offset
        return ([], 0)

    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_FakePool()))
    monkeypatch.setattr(marketplace, "list_plugins_page", fake_list_page)

    await marketplace.list_plugins(
        limit=20,
        offset=40,
        page=99,
        page_size=99,
        category=None,
        pricing_model=None,
        status="approved",
    )

    assert captured == {"limit": 20, "offset": 40}


# --- GET /plugins/search (search_plugins) -----------------------------------


@pytest.mark.asyncio
async def test_search_plugins_forwards_query_and_pagination(monkeypatch):
    captured = {}

    async def fake_search_page(pool, q, limit, offset):
        captured.update(q=q, limit=limit, offset=offset)
        return ([_plugin_response_dict()], 1)

    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_FakePool()))
    monkeypatch.setattr(marketplace, "search_plugins_page", fake_search_page)

    result = await marketplace.search_plugins(
        q="weather", limit=5, offset=0, page=1, page_size=10
    )

    assert captured == {"q": "weather", "limit": 5, "offset": 0}
    assert result.count == 1
    assert result.total == 1


# --- POST /plugins (create_plugin) ------------------------------------------


class _PluginCreateStub:
    name = "test-plugin"
    display_name = "Test Plugin"
    description = None
    author = "tester"
    author_email = None
    repository_url = None
    docker_image = None
    base_tier = "community"
    category_id = None
    developer_id = None
    requires_services: list = []

    class distribution_type:
        value = "git"

    class pricing_model:
        value = "free"


@pytest.mark.asyncio
async def test_create_plugin_success_returns_response(monkeypatch):
    fake_row = {"id": "new-plugin-id", "name": "test-plugin"}
    conn = _FakeConn(row=fake_row)
    monkeypatch.setattr(
        marketplace, "get_pool", AsyncMock(return_value=_FakePool(conn))
    )
    monkeypatch.setattr(
        marketplace, "row_to_plugin_response", lambda row: {"echo": row}
    )

    result = await marketplace.create_plugin(_PluginCreateStub())

    assert result == {"echo": fake_row}
    conn.fetchrow.assert_awaited_once()


# --- GET /plugins/featured (get_featured_plugins) ---------------------------


@pytest.mark.asyncio
async def test_get_featured_plugins_returns_envelope(monkeypatch):
    ids = [str(uuid.uuid4()) for _ in range(3)]

    async def fake_featured(pool, limit):
        assert limit == 3
        return [_plugin_response_dict(id_=i) for i in ids]

    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_FakePool()))
    monkeypatch.setattr(marketplace, "_get_featured_plugins_page", fake_featured)

    result = await marketplace.get_featured_plugins(limit=3)

    assert result.count == 3
    assert [p.id for p in result.plugins] == ids


# --- GET /plugins/{plugin_id} (get_plugin) ----------------------------------


@pytest.mark.asyncio
async def test_get_plugin_returns_the_plugin_when_found(monkeypatch):
    async def fake_get_by_id(pool, plugin_id):
        assert plugin_id == "11111111-1111-1111-1111-111111111111"
        return {"id": plugin_id, "name": "weather"}

    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_FakePool()))
    monkeypatch.setattr(marketplace, "get_plugin_by_id", fake_get_by_id)

    result = await marketplace.get_plugin(
        plugin_id="11111111-1111-1111-1111-111111111111"
    )

    assert result == {"id": "11111111-1111-1111-1111-111111111111", "name": "weather"}


@pytest.mark.asyncio
async def test_get_plugin_404_for_unknown_plugin(monkeypatch):
    async def fake_get_by_id(pool, plugin_id):
        return None

    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_FakePool()))
    monkeypatch.setattr(marketplace, "get_plugin_by_id", fake_get_by_id)

    with pytest.raises(Exception) as exc_info:
        await marketplace.get_plugin(plugin_id="11111111-1111-1111-1111-111111111111")
    assert exc_info.value.status_code == 404


# --- PUT /plugins/{plugin_id} (update_plugin) -------------------------------


@pytest.mark.asyncio
async def test_update_plugin_no_updatable_fields_raises_422():
    empty_update = marketplace.PluginUpdate()

    with pytest.raises(Exception) as exc_info:
        await marketplace.update_plugin(
            empty_update, plugin_id="11111111-1111-1111-1111-111111111111"
        )
    assert exc_info.value.status_code == 422


@pytest.mark.asyncio
async def test_update_plugin_success_binds_params_and_returns_response(monkeypatch):
    fake_row = {"id": "plugin-1", "display_name": "New Name"}
    conn = _FakeConn(row=fake_row)
    monkeypatch.setattr(
        marketplace, "get_pool", AsyncMock(return_value=_FakePool(conn))
    )
    monkeypatch.setattr(
        marketplace, "row_to_plugin_response", lambda row: {"echo": row}
    )

    update = marketplace.PluginUpdate(display_name="New Name")
    result = await marketplace.update_plugin(
        update, plugin_id="11111111-1111-1111-1111-111111111111"
    )

    assert result == {"echo": fake_row}
    args, _ = conn.fetchrow.call_args
    query = args[0]
    assert "display_name = $1" in query
    assert args[1] == "New Name"
    assert args[-1] == "11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_update_plugin_serializes_jsonb_requires_services(monkeypatch):
    fake_row = {"id": "plugin-1", "requires_services": '["ollama"]'}
    conn = _FakeConn(row=fake_row)
    monkeypatch.setattr(
        marketplace, "get_pool", AsyncMock(return_value=_FakePool(conn))
    )
    monkeypatch.setattr(
        marketplace, "row_to_plugin_response", lambda row: {"echo": row}
    )

    update = marketplace.PluginUpdate(requires_services=["ollama"])
    await marketplace.update_plugin(
        update, plugin_id="11111111-1111-1111-1111-111111111111"
    )

    args, _ = conn.fetchrow.call_args
    query = args[0]
    assert "requires_services = $1::jsonb" in query
    assert args[1] == '["ollama"]'  # JSON-serialized, not the raw list


@pytest.mark.asyncio
async def test_update_plugin_404_when_row_not_found(monkeypatch):
    conn = _FakeConn(row=None)
    monkeypatch.setattr(
        marketplace, "get_pool", AsyncMock(return_value=_FakePool(conn))
    )

    update = marketplace.PluginUpdate(display_name="New Name")
    with pytest.raises(Exception) as exc_info:
        await marketplace.update_plugin(
            update, plugin_id="11111111-1111-1111-1111-111111111111"
        )
    assert exc_info.value.status_code == 404
