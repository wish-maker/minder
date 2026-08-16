"""Unit tests for plugin-registry's mutating plugin routes (#351).

#351: install_plugin/enable_plugin/disable_plugin used to return a 200
success response regardless of whether the DB persist actually happened --
update_plugin_in_database swallowed every exception internally, and
install_plugin's webhook-registration failure was only logged, never
propagated. These lock the fix: a persist failure must become a 500, and
enable/disable must not mutate in-memory state before the persist succeeds.

Loaded via sys.path + a stale-cache clear, matching
test_registry_plugin_read_actions.py's precedent.
"""

import json
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


def _build_client(
    *, plugins_db, update_plugin_in_database, register_plugin_webhook=None
):
    routes_plugins = _fresh_import("routes.plugins")
    app = FastAPI()
    app.include_router(
        routes_plugins.build_plugins_router(
            plugins_db=plugins_db,
            plugin_instances={},
            plugin_manifests={},
            webhook_routes={},
            redis_client=None,
            update_plugin_in_database=update_plugin_in_database,
            delete_plugin_from_database=lambda *a, **k: None,
            load_plugin_config=lambda *a, **k: {},
            save_plugin_config=lambda *a, **k: None,
            register_plugin_webhook=register_plugin_webhook or (lambda *a, **k: None),
            handle_webhook_request=lambda *a, **k: None,
            logger=_NoopLogger(),
        )
    )
    app.dependency_overrides[routes_plugins.get_current_user] = lambda: {
        "username": "tester"
    }
    return TestClient(app, raise_server_exceptions=False)


class _Plugin:
    """A minimal stand-in for models.PluginInfo -- enable_plugin/disable_plugin
    only read/mutate `.status`, they never construct or type-check this."""

    def __init__(self, status="registered"):
        self.status = status


def test_enable_plugin_persists_before_mutating_status():
    plugin = _Plugin("registered")
    plugins_db = {"weather": plugin}
    calls = []

    async def fake_update(name, **kwargs):
        calls.append((name, kwargs))

    client = _build_client(plugins_db=plugins_db, update_plugin_in_database=fake_update)

    r = client.post("/v1/plugins/weather/enable")

    assert r.status_code == 200
    assert plugin.status == "enabled"
    assert calls == [("weather", {"status": "enabled", "enabled": True})]


def test_enable_plugin_returns_500_and_does_not_mutate_status_on_db_failure():
    plugin = _Plugin("registered")
    plugins_db = {"weather": plugin}

    async def fake_update(name, **kwargs):
        raise RuntimeError("db connection lost")

    client = _build_client(plugins_db=plugins_db, update_plugin_in_database=fake_update)

    r = client.post("/v1/plugins/weather/enable")

    assert r.status_code == 500
    # Must NOT have flipped to "enabled" while the DB write actually failed.
    assert plugin.status == "registered"


def test_disable_plugin_returns_500_on_db_failure():
    plugin = _Plugin("enabled")
    plugins_db = {"weather": plugin}

    async def fake_update(name, **kwargs):
        raise RuntimeError("db connection lost")

    client = _build_client(plugins_db=plugins_db, update_plugin_in_database=fake_update)

    r = client.post("/v1/plugins/weather/disable")

    assert r.status_code == 500
    assert plugin.status == "enabled"


def test_install_plugin_returns_500_when_webhook_registration_fails():
    plugins_db = {}

    async def fake_update(name, **kwargs):
        return None

    async def fake_register(name, manifest):
        raise RuntimeError("webhook route conflict")

    client = _build_client(
        plugins_db=plugins_db,
        update_plugin_in_database=fake_update,
        register_plugin_webhook=fake_register,
    )

    manifest = {
        "metadata": {"name": "weather", "version": "1.0.0"},
        "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/weather"}}},
    }
    r = client.post(
        "/v1/plugins/install",
        content=json.dumps(manifest),
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 500


def test_install_plugin_succeeds_when_webhook_registration_succeeds():
    plugins_db = {}

    async def fake_update(name, **kwargs):
        return None

    async def fake_register(name, manifest):
        return None

    client = _build_client(
        plugins_db=plugins_db,
        update_plugin_in_database=fake_update,
        register_plugin_webhook=fake_register,
    )

    manifest = {
        "metadata": {"name": "weather", "version": "1.0.0"},
        "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/weather"}}},
    }
    r = client.post(
        "/v1/plugins/install",
        content=json.dumps(manifest),
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 200
    assert "weather" in plugins_db


# --- install/reload-webhook auth gate -----------------------------------------
#
# Found in a background audit: install_plugin and reload_plugin_webhook were the
# only two mutating routes in this file with no Depends(get_current_user) at
# all -- every sibling (uninstall/enable/disable/collect/actions/config PUT)
# already requires it. plugin-registry is reachable directly by any container
# on the docker network (the same #405 class of gap already fixed for
# plugin-state-manager/model-management/marketplace this session), not just
# through api-gateway's own _require_jwt_for_writes gate on the proxied path.
# These build the client WITHOUT the dependency_overrides bypass the other
# tests in this file use, so the real auth gate is what's under test.


def _build_client_no_auth_override(
    *, plugins_db, update_plugin_in_database, register_plugin_webhook=None
):
    routes_plugins = _fresh_import("routes.plugins")
    app = FastAPI()
    app.include_router(
        routes_plugins.build_plugins_router(
            plugins_db=plugins_db,
            plugin_instances={},
            plugin_manifests={},
            webhook_routes={},
            redis_client=None,
            update_plugin_in_database=update_plugin_in_database,
            delete_plugin_from_database=lambda *a, **k: None,
            load_plugin_config=lambda *a, **k: {},
            save_plugin_config=lambda *a, **k: None,
            register_plugin_webhook=register_plugin_webhook or (lambda *a, **k: None),
            handle_webhook_request=lambda *a, **k: None,
            logger=_NoopLogger(),
        )
    )
    return TestClient(app, raise_server_exceptions=False)


def test_install_plugin_requires_auth():
    plugins_db = {}
    client = _build_client_no_auth_override(
        plugins_db=plugins_db, update_plugin_in_database=lambda *a, **k: None
    )
    manifest = {
        "metadata": {"name": "weather", "version": "1.0.0"},
        "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/weather"}}},
    }
    r = client.post(
        "/v1/plugins/install",
        content=json.dumps(manifest),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 401
    assert "weather" not in plugins_db  # request never reached the handler body


def test_reload_plugin_webhook_requires_auth():
    plugins_db = {"weather": _Plugin("enabled")}
    client = _build_client_no_auth_override(
        plugins_db=plugins_db, update_plugin_in_database=lambda *a, **k: None
    )
    manifest = {
        "metadata": {"name": "weather", "version": "1.0.0"},
        "spec": {"trigger": {"type": "webhook", "webhook": {"path": "/weather"}}},
    }
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=json.dumps(manifest),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 401
