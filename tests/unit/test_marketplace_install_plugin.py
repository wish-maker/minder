"""Unit tests for POST /v1/marketplace/plugins/{id}/install (#402).

Found live on hantal even after fixing the FK-violation bug and the
InstallationResponse.user_id UUID-pattern bug: install_plugin never str()-cast
plugin_id before constructing its response. asyncpg returns UUID columns as
uuid.UUID objects, and InstallationResponse.plugin_id is a `str` field --
pydantic v2 does not coerce UUID -> str (confirmed: raises string_type), so
this 500'd on response serialization for every real install, in BOTH the
new-installation and already-installed branches.

Isolated-import pattern matches test_marketplace_error_handling.py /
test_marketplace_my_installations.py.
"""

import sys
import uuid
from datetime import datetime, timezone
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


(management,) = _isolated_import("routes.management")


class _FakeConn:
    def __init__(self, plugin_row, existing_row, insert_row):
        self._plugin_row = plugin_row
        self._existing_row = existing_row
        self._insert_row = insert_row

    async def fetchrow(self, query, *args):
        if "FROM marketplace_plugins" in query:
            return self._plugin_row
        if "FROM marketplace_installations" in query and "SELECT" in query:
            return self._existing_row
        if "INSERT INTO marketplace_installations" in query:
            return self._insert_row
        return None

    async def execute(self, query, *args):
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


def _uuid_row(plugin_id, **overrides):
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


@pytest.mark.asyncio
async def test_new_installation_does_not_500_on_uuid_plugin_id(monkeypatch):
    plugin_id = str(uuid.uuid4())
    plugin_row = {"id": uuid.UUID(plugin_id), "name": "test-plugin"}
    insert_row = _uuid_row(uuid.UUID(plugin_id))
    conn = _FakeConn(plugin_row, existing_row=None, insert_row=insert_row)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(plugin_id, current_user={"sub": "4"})

    assert result.plugin_id == plugin_id
    assert result.status == "installed"


@pytest.mark.asyncio
async def test_reinstall_existing_does_not_500_on_uuid_plugin_id(monkeypatch):
    plugin_id = str(uuid.uuid4())
    plugin_row = {"id": uuid.UUID(plugin_id), "name": "test-plugin"}
    existing_row = _uuid_row(uuid.UUID(plugin_id))
    conn = _FakeConn(plugin_row, existing_row=existing_row, insert_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(plugin_id, current_user={"sub": "4"})

    assert result.plugin_id == plugin_id
    assert result.enabled is True
