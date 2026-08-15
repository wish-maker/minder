"""Unit tests for uninstall_plugin's webhook_routes/plugin_manifests cleanup (#639).

uninstall_plugin used to only touch plugins_db + a redis key -- webhook_routes
and plugin_manifests (both populated by register_plugin_webhook) were never
cleaned up, so handle_webhook_request (which only checks those two dicts,
never plugins_db) kept matching and executing the "uninstalled" plugin's
webhook. This locks in the fix: both dicts must be cleared for the uninstalled
plugin, and untouched for every other plugin.

Loaded via sys.path + a stale-cache clear, matching
test_registry_plugin_write_actions.py's precedent.
"""

import sys
from pathlib import Path
from types import ModuleType

from fastapi import FastAPI
from fastapi.testclient import TestClient

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    for stale in list(sys.modules):
        if (
            stale == "core"
            or stale.startswith("core.")
            or stale == "routes"
            or stale.startswith("routes.")
            or stale == "schemas"
            or stale.startswith("schemas.")
            or stale in ("config", "models")
        ):
            del sys.modules[stale]
    fake_schemas = ModuleType("schemas")
    fake_validator = ModuleType("schemas.validator")
    fake_validator.validate_manifest = lambda *a, **k: (True, [])
    fake_schemas.validator = fake_validator
    sys.modules["schemas"] = fake_schemas
    sys.modules["schemas.validator"] = fake_validator

    import importlib

    return importlib.import_module(module_path)


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _FakeRedis:
    def __init__(self):
        self.deleted = []

    def delete(self, key):
        self.deleted.append(key)


def _build_client(*, plugins_db, plugin_manifests, webhook_routes, redis_client):
    routes_plugins = _fresh_import("routes.plugins")
    app = FastAPI()
    app.include_router(
        routes_plugins.build_plugins_router(
            plugins_db=plugins_db,
            plugin_instances={},
            plugin_manifests=plugin_manifests,
            webhook_routes=webhook_routes,
            redis_client=redis_client,
            update_plugin_in_database=lambda *a, **k: None,
            load_plugin_config=lambda *a, **k: {},
            save_plugin_config=lambda *a, **k: None,
            register_plugin_webhook=lambda *a, **k: None,
            handle_webhook_request=lambda *a, **k: None,
            logger=_NoopLogger(),
        )
    )
    app.dependency_overrides[routes_plugins.get_current_user] = lambda: {
        "username": "tester"
    }
    return TestClient(app, raise_server_exceptions=False)


class _Plugin:
    def __init__(self, status="enabled"):
        self.status = status


def test_uninstall_removes_the_plugins_own_manifest_and_webhook_route():
    plugins_db = {"weather": _Plugin()}
    plugin_manifests = {"weather": {"metadata": {"name": "weather"}}}
    webhook_routes = {"/webhook/weather": "weather"}
    redis_client = _FakeRedis()

    client = _build_client(
        plugins_db=plugins_db,
        plugin_manifests=plugin_manifests,
        webhook_routes=webhook_routes,
        redis_client=redis_client,
    )

    r = client.delete("/v1/plugins/weather")

    assert r.status_code == 200
    assert "weather" not in plugins_db
    assert "weather" not in plugin_manifests
    assert "/webhook/weather" not in webhook_routes
    assert redis_client.deleted == ["plugin:weather"]


def test_uninstall_leaves_other_plugins_manifests_and_routes_untouched():
    plugins_db = {"weather": _Plugin(), "news": _Plugin()}
    plugin_manifests = {
        "weather": {"metadata": {"name": "weather"}},
        "news": {"metadata": {"name": "news"}},
    }
    webhook_routes = {"/webhook/weather": "weather", "/webhook/news": "news"}
    redis_client = _FakeRedis()

    client = _build_client(
        plugins_db=plugins_db,
        plugin_manifests=plugin_manifests,
        webhook_routes=webhook_routes,
        redis_client=redis_client,
    )

    r = client.delete("/v1/plugins/weather")

    assert r.status_code == 200
    assert "news" in plugins_db
    assert "news" in plugin_manifests
    assert "/webhook/news" in webhook_routes


def test_uninstall_is_a_noop_safe_when_the_plugin_had_no_webhook():
    """A plugin with no webhook trigger never appears in webhook_routes/
    plugin_manifests at all -- uninstall must not raise on the missing keys."""
    plugins_db = {"weather": _Plugin()}
    plugin_manifests: dict = {}
    webhook_routes: dict = {}
    redis_client = _FakeRedis()

    client = _build_client(
        plugins_db=plugins_db,
        plugin_manifests=plugin_manifests,
        webhook_routes=webhook_routes,
        redis_client=redis_client,
    )

    r = client.delete("/v1/plugins/weather")

    assert r.status_code == 200
    assert "weather" not in plugins_db
