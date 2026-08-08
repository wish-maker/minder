"""Unit tests for marketplace's error handling (#357).

#357: create_plugin (routes/marketplace.py), sync_ai_tools's generic
catch-all, and deactivate_plugin_tools (routes/ai_tools.py) all caught a
generic Exception and returned HTTPException(500, detail=f"...: {str(e)}") --
leaking the raw asyncpg/driver exception string. Switched to
shared.errors.backend_http_error.

No DB: get_pool() is monkeypatched to a fake pool whose acquire() raises.
"""

import sys
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


ai_tools, marketplace = _isolated_import("routes.ai_tools", "routes.marketplace")


class _BoomAcquire:
    async def __aenter__(self):
        raise ConnectionError(_SECRET)

    async def __aexit__(self, *exc):
        return False


class _BoomPool:
    def acquire(self):
        return _BoomAcquire()


_SECRET = "postgresql://minder:hunter2@10.0.0.5:5432/minder unreachable"


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

    class distribution_type:
        value = "git"

    class pricing_model:
        value = "free"


@pytest.mark.asyncio
async def test_create_plugin_db_failure_does_not_leak_exception_text(monkeypatch):
    monkeypatch.setattr(marketplace, "get_pool", AsyncMock(return_value=_BoomPool()))

    with pytest.raises(Exception) as exc_info:
        await marketplace.create_plugin(_PluginCreateStub())

    assert exc_info.value.status_code == 503
    assert _SECRET not in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_sync_ai_tools_generic_failure_does_not_leak_exception_text(
    monkeypatch,
):
    async def boom(**kwargs):
        raise ConnectionError(_SECRET)

    monkeypatch.setattr(ai_tools, "sync_plugin_tools", boom)

    request = ai_tools.AIToolsSyncRequest(
        plugin_name="crypto", plugin_id="plugin-1", manifest={}
    )

    with pytest.raises(Exception) as exc_info:
        await ai_tools.sync_ai_tools(request, current_user={"username": "svc"})

    assert exc_info.value.status_code == 503
    assert _SECRET not in str(exc_info.value.detail)


# deactivate_plugin_tools (routes/ai_tools.py) uses the identical
# backend_http_error pattern as sync_ai_tools above, but does `from
# core.ai_tools_importer import ...` INSIDE the function body (a lazy import)
# -- re-resolving via sys.path on every call, which this test harness's
# module-collision isolation can't reliably keep working across the full
# suite (other test files' own isolated imports evict the same cached
# module). Not tested directly here; the pattern is already proven by the two
# tests above.


def test_plugin_updatable_whitelist_includes_author():
    """Regression guard (#402): `author` was missing from both PluginUpdate and
    this route's column whitelist, so a stale placeholder "Unknown" author
    (from before the marketplace-sync fix in #404) could never be corrected
    even via PUT /v1/marketplace/plugins/{id} -- confirmed live while
    backfilling the Pi's pre-existing entries. If this regresses, author
    becomes silently unfixable again."""
    assert "author" in marketplace._PLUGIN_UPDATABLE
