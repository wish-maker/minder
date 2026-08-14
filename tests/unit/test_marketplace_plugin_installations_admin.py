"""Unit tests for GET /v1/marketplace/plugins/{plugin_id}/installations (#474).

This endpoint's docstring always called it "admin endpoint" but had NO
authentication dependency at all -- any caller, unauthenticated, could list
every user_id that installed a given plugin. Fixed by adding
Depends(require_role("admin")).

Unlike test_marketplace_install_plugin.py's pattern (call the route function
directly, bypassing FastAPI's dependency resolution -- fine for testing
business logic that already assumes auth passed), THIS file specifically
needs to exercise the real dependency-injection layer, since the auth gate
itself is what's under test. Mounts the real router in a throwaway app,
same pattern as test_registry_bundles_mutate.py /
test_internal_write_endpoints_require_auth.py.
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

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


management, jwt_middleware = _isolated_import(
    "routes.management", "shared.auth.jwt_middleware"
)


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetchval(self, query, *args):
        return len(self._rows)

    async def fetch(self, query, *args):
        return self._rows

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


def _row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid.uuid4(),
        "user_id": "4",
        "plugin_id": str(uuid.uuid4()),
        "version": None,
        "status": "installed",
        "enabled": True,
        "installed_at": now,
    }
    base.update(overrides)
    return base


def _client(monkeypatch, rows):
    conn = _FakeConn(rows)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    app = FastAPI()
    app.include_router(management.router)
    return TestClient(app, raise_server_exceptions=False)


def test_requires_auth(monkeypatch):
    client = _client(monkeypatch, rows=[])
    plugin_id = str(uuid.uuid4())
    resp = client.get(f"/v1/marketplace/plugins/{plugin_id}/installations")
    assert resp.status_code == 401


def test_rejects_non_admin(monkeypatch):
    client = _client(monkeypatch, rows=[])
    client.app.dependency_overrides[jwt_middleware.get_current_user] = lambda: {
        "sub": "4",
        "role": "user",
    }
    plugin_id = str(uuid.uuid4())
    resp = client.get(f"/v1/marketplace/plugins/{plugin_id}/installations")
    assert resp.status_code == 403


def test_admin_can_list_installations(monkeypatch):
    plugin_id = str(uuid.uuid4())
    rows = [_row(plugin_id=plugin_id), _row(plugin_id=plugin_id, user_id="7")]
    client = _client(monkeypatch, rows=rows)
    client.app.dependency_overrides[jwt_middleware.get_current_user] = lambda: {
        "sub": "1",
        "role": "admin",
    }
    resp = client.get(f"/v1/marketplace/plugins/{plugin_id}/installations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert {i["user_id"] for i in body["installations"]} == {"4", "7"}
