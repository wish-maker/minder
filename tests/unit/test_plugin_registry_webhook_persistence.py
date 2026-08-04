"""Unit tests for webhook manifest persistence (plugin-registry, #269).

register_all_webhooks_on_startup() previously relied on in-memory state plus a
"/tmp/*-manifest.yml" restart-safety workaround -- registered webhook routes
were lost on every registry restart until plugins re-registered themselves.
These lock the PostgreSQL-backed replacement: every registration persists via
save_plugin_manifest(), and startup restores from load_all_plugin_manifests()
(only for plugins still present in plugins_db).

Loaded via sys.path + a stale-cache clear (not spec_from_file_location): unlike
the single-file rag-pipeline/tts-stt precedents, webhooks.py internally does
`from core.database import ...` -- a package-qualified import that needs a real
`core` package on sys.path, not just a uniquely-named single module. Clearing
any stale core/config/models entries first (conftest.py loads every service's
main.py into ONE shared pytest process) ensures a fresh, correctly-scoped
import instead of picking up another service's same-named package.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    for stale in list(sys.modules):
        if (
            stale == "core"
            or stale.startswith("core.")
            or stale in ("config", "models")
        ):
            del sys.modules[stale]
    import importlib

    return importlib.import_module(module_path)


# webhooks.py does `from core.database import ...`, so importing it transitively
# imports core.database as a side effect -- grab THAT instance from sys.modules
# afterward rather than importing core.database separately (a second, separate
# _fresh_import call would clear the cache again and produce a second, distinct
# module object whose get_postgres_connection monkeypatches below wouldn't reach).
webhooks = _fresh_import("core.webhooks")
database = sys.modules["core.database"]


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


@pytest.fixture
def fake_pool(monkeypatch):
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    pool = _FakePool(conn)
    monkeypatch.setattr(
        database, "get_postgres_connection", AsyncMock(return_value=pool)
    )
    return conn


@pytest.mark.asyncio
async def test_save_plugin_manifest_upserts(fake_pool):
    manifest = {"metadata": {"name": "weather"}, "spec": {}}
    await database.save_plugin_manifest("weather", manifest)

    fake_pool.execute.assert_called_once()
    query, plugin_name, manifest_json = fake_pool.execute.call_args.args
    assert "INSERT INTO plugin_manifests" in query
    assert "ON CONFLICT (plugin_name) DO UPDATE" in query
    assert plugin_name == "weather"
    assert '"name": "weather"' in manifest_json


@pytest.mark.asyncio
async def test_save_plugin_manifest_swallows_db_errors(monkeypatch):
    async def _boom():
        raise ConnectionError("db down")

    monkeypatch.setattr(database, "get_postgres_connection", _boom)
    # Must not raise -- a save failure shouldn't break plugin registration.
    await database.save_plugin_manifest("weather", {"metadata": {"name": "weather"}})


@pytest.mark.asyncio
async def test_load_all_plugin_manifests_parses_dict_and_json_string(fake_pool):
    fake_pool.fetch.return_value = [
        {"plugin_name": "weather", "manifest": {"metadata": {"name": "weather"}}},
        {"plugin_name": "news", "manifest": '{"metadata": {"name": "news"}}'},
    ]
    result = await webhooks.load_all_plugin_manifests()
    assert result == {
        "weather": {"metadata": {"name": "weather"}},
        "news": {"metadata": {"name": "news"}},
    }


@pytest.mark.asyncio
async def test_load_all_plugin_manifests_returns_empty_on_error(monkeypatch):
    async def _boom():
        raise ConnectionError("db down")

    monkeypatch.setattr(database, "get_postgres_connection", _boom)
    assert await webhooks.load_all_plugin_manifests() == {}


@pytest.mark.asyncio
async def test_register_plugin_webhook_persists_manifest(monkeypatch):
    saved = []

    async def _fake_save(plugin_name, manifest):
        saved.append((plugin_name, manifest))

    monkeypatch.setattr(webhooks, "save_plugin_manifest", _fake_save)
    monkeypatch.setattr(webhooks, "webhook_routes", {})
    monkeypatch.setattr(webhooks, "plugin_manifests", {})

    manifest = {
        "metadata": {"name": "weather"},
        "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/weather"}}},
    }
    await webhooks.register_plugin_webhook("weather", manifest)

    assert saved == [("weather", manifest)]
    assert webhooks.webhook_routes == {"/webhook/weather": "weather"}


@pytest.mark.asyncio
async def test_register_plugin_webhook_skips_persist_for_non_webhook_manifest(
    monkeypatch,
):
    saved = []
    monkeypatch.setattr(
        webhooks, "save_plugin_manifest", lambda *a: saved.append(a) or None
    )
    monkeypatch.setattr(webhooks, "webhook_routes", {})
    monkeypatch.setattr(webhooks, "plugin_manifests", {})

    await webhooks.register_plugin_webhook(
        "weather",
        {"metadata": {"name": "weather"}, "spec": {"trigger": {"type": "schedule"}}},
    )

    assert saved == []
    assert webhooks.webhook_routes == {}


@pytest.mark.asyncio
async def test_register_all_webhooks_on_startup_restores_only_known_plugins(
    monkeypatch,
):
    persisted = {
        "weather": {
            "metadata": {"name": "weather"},
            "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/weather"}}},
        },
        "removed-plugin": {
            "metadata": {"name": "removed-plugin"},
            "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/gone"}}},
        },
    }
    monkeypatch.setattr(
        webhooks, "load_all_plugin_manifests", AsyncMock(return_value=persisted)
    )
    monkeypatch.setattr(webhooks, "plugins_db", {"weather": object()})
    monkeypatch.setattr(webhooks, "plugin_manifests", {})
    monkeypatch.setattr(webhooks, "webhook_routes", {})
    monkeypatch.setattr(webhooks, "save_plugin_manifest", AsyncMock())

    await webhooks.register_all_webhooks_on_startup()

    assert webhooks.webhook_routes == {"/webhook/weather": "weather"}
    assert "removed-plugin" not in webhooks.plugin_manifests
