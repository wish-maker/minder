"""Unit tests for GET /v1/marketplace/installations/me (#402).

Before this endpoint existed, there was no way for a user to list their own
installed plugins across the whole catalog -- GET /plugins/{id}/installations
is the wrong shape (per-plugin, all-users). Registered under a disjoint
/v1/marketplace/installations prefix, not nested under /v1/marketplace/plugins/,
since GET /plugins/{plugin_id} (routes/marketplace.py) is registered first and
would swallow a literal path segment as {plugin_id} otherwise.

Isolated-import pattern matches test_marketplace_error_handling.py.
"""

import sys
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


(installations,) = _isolated_import("routes.installations")


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

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
    def __init__(self, rows):
        self._rows = rows

    def acquire(self):
        return _FakeAcquire(_FakeConn(self._rows))


def _row(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "installation_id": "550e8400-e29b-41d4-a716-446655440000",
        "plugin_id": "550e8400-e29b-41d4-a716-446655440001",
        "version": "1.0.0",
        "status": "installed",
        "enabled": True,
        "installed_at": now,
        "last_updated_at": now,
        "name": "weather",
        "display_name": "Weather",
        "description": "Polls a weather API.",
        "current_version": "1.0.0",
        "pricing_model": "free",
        "base_tier": "community",
        "category_id": None,
        "author": "Minder Team",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_returns_installations_with_inlined_plugin_metadata(monkeypatch):
    rows = [_row()]
    monkeypatch.setattr(
        installations, "get_pool", AsyncMock(return_value=_FakePool(rows))
    )

    result = await installations.get_my_installations(current_user={"sub": "4"})

    assert result.count == 1
    entry = result.installations[0]
    assert entry.installation_id == "550e8400-e29b-41d4-a716-446655440000"
    assert entry.plugin_id == "550e8400-e29b-41d4-a716-446655440001"
    assert entry.name == "weather"
    assert entry.display_name == "Weather"


@pytest.mark.asyncio
async def test_non_uuid_user_id_does_not_break_response_serialization(monkeypatch):
    # Regression guard: InstallationResponse.user_id used to have a UUID-only
    # regex pattern, rejecting real JWT-derived ids like "4" or "admin". This
    # endpoint doesn't even return user_id, but confirm a non-UUID `sub` (the
    # realistic shape) flows through cleanly end to end.
    rows = [_row()]
    monkeypatch.setattr(
        installations, "get_pool", AsyncMock(return_value=_FakePool(rows))
    )

    result = await installations.get_my_installations(current_user={"sub": "admin"})

    assert result.count == 1


@pytest.mark.asyncio
async def test_empty_when_nothing_installed(monkeypatch):
    monkeypatch.setattr(
        installations, "get_pool", AsyncMock(return_value=_FakePool([]))
    )

    result = await installations.get_my_installations(current_user={"sub": "4"})

    assert result.count == 0
    assert result.installations == []
