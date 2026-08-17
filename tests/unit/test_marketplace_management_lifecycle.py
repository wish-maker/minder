"""Unit tests filling routes/management.py's remaining coverage gaps (60%).

test_marketplace_install_plugin.py already locks in install_plugin's UUID-
serialization fix and the MAX_PLUGINS_PER_USER cap. test_marketplace_plugin_
installations_admin.py covers the admin listing endpoint. This adds
everything else: install_plugin's plugin-not-found 404, and the entire
uninstall/enable/disable trio (not-installed 404 + success path for each --
none of the three had ANY coverage before this).

Same isolated-import + fake-pool pattern as the sibling suite. Routes are
called directly as plain async functions (bypassing FastAPI's Depends/routing
layer), matching test_marketplace_install_plugin.py's precedent.
"""

import sys
import uuid
from datetime import datetime, timezone
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


(management,) = _isolated_import("routes.management")


class _FakeConn:
    def __init__(self, plugin_row=None, existing_row=None):
        self._plugin_row = plugin_row
        self._existing_row = existing_row
        self.executed = []

    async def fetchrow(self, query, *args):
        if "FROM marketplace_plugins" in query:
            return self._plugin_row
        if "FROM marketplace_installations" in query and "SELECT *" in query:
            return self._existing_row
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


def _installation_row(plugin_id, **overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid.uuid4(),
        "user_id": "4",
        "plugin_id": plugin_id,
        "version": None,
        "status": "installed",
        "enabled": True,
        "config_json": None,
        "installed_at": now,
        "last_updated_at": now,
    }
    base.update(overrides)
    return base


# --- install_plugin: plugin-not-found 404 ------------------------------------


@pytest.mark.asyncio
async def test_install_plugin_404_when_plugin_does_not_exist(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(plugin_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.install_plugin(plugin_id, current_user={"sub": "4"})

    assert exc.value.status_code == 404


# --- uninstall_plugin ----------------------------------------------------------


@pytest.mark.asyncio
async def test_uninstall_plugin_404_when_not_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.uninstall_plugin(plugin_id, current_user={"sub": "4"})

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_uninstall_plugin_success_updates_status(monkeypatch):
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.uninstall_plugin(plugin_id, current_user={"sub": "4"})

    assert result == {"status": "uninstalled", "plugin_id": plugin_id}
    query, args = conn.executed[0]
    assert "SET status = 'uninstalled'" in query
    assert args == (existing["id"],)


# --- enable_plugin ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_plugin_404_when_not_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.enable_plugin(plugin_id, current_user={"sub": "4"})

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_enable_plugin_success_updates_enabled(monkeypatch):
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.enable_plugin(plugin_id, current_user={"sub": "4"})

    assert result == {"status": "enabled", "plugin_id": plugin_id}
    query, args = conn.executed[0]
    assert "SET enabled = TRUE" in query
    assert args == (existing["id"],)


# --- disable_plugin --------------------------------------------------------------


@pytest.mark.asyncio
async def test_disable_plugin_404_when_not_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.disable_plugin(plugin_id, current_user={"sub": "4"})

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_disable_plugin_success_updates_enabled(monkeypatch):
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.disable_plugin(plugin_id, current_user={"sub": "4"})

    assert result == {"status": "disabled", "plugin_id": plugin_id}
    query, args = conn.executed[0]
    assert "SET enabled = FALSE" in query
    assert args == (existing["id"],)
