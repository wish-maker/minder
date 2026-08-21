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
    def __init__(self, plugin_row, existing_row, insert_row, install_count=0):
        self._plugin_row = plugin_row
        self._existing_row = existing_row
        self._insert_row = insert_row
        self._install_count = install_count

    async def fetchrow(self, query, *args):
        if "FROM marketplace_plugins" in query:
            return self._plugin_row
        if "INSERT INTO marketplace_installations" in query:
            return self._insert_row
        if "UPDATE marketplace_installations" in query and "RETURNING" in query:
            # #892: install_plugin's own dependency check (_ensure_dependencies_
            # enabled) flips the row to enabled=TRUE via an UPDATE...RETURNING
            # after writing it with enabled=FALSE first -- these tests default
            # to a dependency-free _FakeNeo4j (see install_plugin() call sites
            # below), so the check always passes; return whichever row this
            # conn was constructed with, enabled.
            base = (
                self._insert_row if self._insert_row is not None else self._existing_row
            )
            if base is None:
                return None
            updated = dict(base)
            updated["enabled"] = True
            return updated
        if "FROM marketplace_installations" in query and "SELECT *" in query:
            return self._existing_row
        return None

    async def fetchval(self, query, *args):
        if "COUNT(*) FROM marketplace_installations" in query:
            return self._install_count
        return None

    async def execute(self, query, *args):
        return None

    async def fetch(self, query, *args):
        return []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeNeo4j:
    """No declared dependencies -- #892's install_plugin dependency check is
    exercised for real (with actual dependencies) in
    test_marketplace_management_lifecycle.py; this file's own tests predate
    #748/#892 and only need the check to be a no-op pass-through."""

    async def get_dependency_chain(self, plugin_id):
        return []


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
    plugin_row = {
        "id": uuid.UUID(plugin_id),
        "name": "test-plugin",
        "status": "approved",
    }
    insert_row = _uuid_row(uuid.UUID(plugin_id))
    conn = _FakeConn(plugin_row, existing_row=None, insert_row=insert_row)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(
        current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
    )

    assert result.plugin_id == plugin_id
    assert result.status == "installed"


@pytest.mark.asyncio
async def test_reinstall_existing_does_not_500_on_uuid_plugin_id(monkeypatch):
    plugin_id = str(uuid.uuid4())
    plugin_row = {
        "id": uuid.UUID(plugin_id),
        "name": "test-plugin",
        "status": "approved",
    }
    existing_row = _uuid_row(uuid.UUID(plugin_id))
    conn = _FakeConn(plugin_row, existing_row=existing_row, insert_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(
        current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
    )

    assert result.plugin_id == plugin_id
    assert result.enabled is True


@pytest.mark.asyncio
async def test_install_rejected_once_user_hits_max_plugins_per_user(monkeypatch):
    """MAX_PLUGINS_PER_USER was defined in config but never enforced anywhere --
    a single user could install every plugin in the catalog with no limit."""
    monkeypatch.setattr(management.settings, "MAX_PLUGINS_PER_USER", 2)
    plugin_id = str(uuid.uuid4())
    plugin_row = {
        "id": uuid.UUID(plugin_id),
        "name": "test-plugin",
        "status": "approved",
    }
    conn = _FakeConn(plugin_row, existing_row=None, insert_row=None, install_count=2)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await management.install_plugin(
            current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
        )

    assert exc.value.status_code == 409
    assert "limit" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_install_allowed_when_under_max_plugins_per_user(monkeypatch):
    monkeypatch.setattr(management.settings, "MAX_PLUGINS_PER_USER", 2)
    plugin_id = str(uuid.uuid4())
    plugin_row = {
        "id": uuid.UUID(plugin_id),
        "name": "test-plugin",
        "status": "approved",
    }
    insert_row = _uuid_row(uuid.UUID(plugin_id))
    conn = _FakeConn(
        plugin_row, existing_row=None, insert_row=insert_row, install_count=1
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(
        current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
    )

    assert result.status == "installed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status", ["draft", "submitted", "in_review", "rejected", "archived"]
)
async def test_install_rejects_a_non_approved_plugin_with_404(monkeypatch, status):
    """#938: only an `approved` listing is installable. A draft/rejected/
    archived plugin is hidden on read; install must 404 it too (not reveal it
    exists), rather than let anyone with the id install an unapproved listing."""
    from fastapi import HTTPException

    plugin_id = str(uuid.uuid4())
    plugin_row = {"id": uuid.UUID(plugin_id), "name": "test-plugin", "status": status}
    conn = _FakeConn(plugin_row, existing_row=None, insert_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.install_plugin(
            current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reinstall_of_existing_plugin_is_not_capped_by_max_plugins_per_user(
    monkeypatch,
):
    """Re-enabling an already-installed plugin (the `existing` branch) must not
    be blocked by the cap -- it doesn't add a new installation row."""
    monkeypatch.setattr(management.settings, "MAX_PLUGINS_PER_USER", 1)
    plugin_id = str(uuid.uuid4())
    plugin_row = {
        "id": uuid.UUID(plugin_id),
        "name": "test-plugin",
        "status": "approved",
    }
    existing_row = _uuid_row(uuid.UUID(plugin_id))
    # install_count would be over the (artificially low) cap if this path
    # incorrectly re-checked it -- proves the existing-row branch returns
    # before ever reaching the cap check.
    conn = _FakeConn(
        plugin_row, existing_row=existing_row, insert_row=None, install_count=5
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(
        current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
    )

    assert result.status == "installed"
