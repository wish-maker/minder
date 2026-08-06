"""Unit tests for the plugin-registry read-only action route (#254).

`POST /v1/plugins/{plugin}/actions/{action}` was the only way to invoke ANY
plugin action, mutating or not, and required a JWT — so read-only data tools
(get_crypto_price, get_weather, ...) were gated behind auth purely because they
shared a route with real mutations. `GET /v1/plugins/{plugin}/actions/{action}`
adds an unauthenticated path, reachable only for actions a plugin explicitly
lists in READ_ONLY_ACTIONS (a declared subset of ACTIONS); the POST route is
unchanged (still JWT-gated, still serves both read and mutating actions).

Loaded via sys.path + a stale-cache clear, matching
test_plugin_registry_webhook_persistence.py's precedent: routes/plugins.py
does package-qualified imports (`from models import PluginInfo`, `from core
import plugin_config`, `from schemas.validator import validate_manifest`) that
need the real plugin-registry package tree on sys.path, not just this one file.
"""

import sys
from pathlib import Path
from types import ModuleType

import pytest
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
    # routes/plugins.py does `from schemas.validator import validate_manifest`, which
    # pulls in the real jsonschema package -- irrelevant to these tests (manifest
    # validation isn't exercised here) and not guaranteed present in every test env.
    # Fake it out, matching this suite's established precedent for faking `models`.
    fake_schemas = ModuleType("schemas")
    fake_validator = ModuleType("schemas.validator")
    fake_validator.validate_manifest = lambda *a, **k: None
    fake_schemas.validator = fake_validator
    sys.modules["schemas"] = fake_schemas
    sys.modules["schemas.validator"] = fake_validator

    import importlib

    return importlib.import_module(module_path)


class _FakePlugin:
    ACTIONS = frozenset({"refresh", "get_price"})
    READ_ONLY_ACTIONS = frozenset({"get_price"})

    def __init__(self):
        self.refresh_calls = 0

    async def refresh(self):
        self.refresh_calls += 1
        return {"refreshed": True}

    def get_price(self, coin: str):
        if coin == "boom":
            raise ValueError("unknown coin")
        return {"coin": coin, "price": 42}


@pytest.fixture
def client():
    routes_plugins = _fresh_import("routes.plugins")

    class _NoopLogger:
        def info(self, *a, **k):
            pass

        def error(self, *a, **k):
            pass

    instance = _FakePlugin()
    plugins_db = {"crypto": object()}
    plugin_instances = {"crypto": instance}

    app = FastAPI()
    app.include_router(
        routes_plugins.build_plugins_router(
            plugins_db=plugins_db,
            plugin_instances=plugin_instances,
            plugin_manifests={},
            webhook_routes={},
            redis_client=None,
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
    with_auth = TestClient(app, raise_server_exceptions=True)

    app_no_auth = FastAPI()
    app_no_auth.include_router(
        routes_plugins.build_plugins_router(
            plugins_db=plugins_db,
            plugin_instances=plugin_instances,
            plugin_manifests={},
            webhook_routes={},
            redis_client=None,
            update_plugin_in_database=lambda *a, **k: None,
            load_plugin_config=lambda *a, **k: {},
            save_plugin_config=lambda *a, **k: None,
            register_plugin_webhook=lambda *a, **k: None,
            handle_webhook_request=lambda *a, **k: None,
            logger=_NoopLogger(),
        )
    )
    without_auth = TestClient(app_no_auth, raise_server_exceptions=True)

    return with_auth, without_auth, instance


def test_get_read_only_action_unauthenticated(client):
    _, without_auth, _ = client
    r = without_auth.get("/v1/plugins/crypto/actions/get_price", params={"coin": "btc"})
    assert r.status_code == 200
    assert r.json() == {
        "plugin": "crypto",
        "action": "get_price",
        "result": {"coin": "btc", "price": 42},
    }


def test_get_mutating_action_rejected_even_unauthenticated(client):
    _, without_auth, instance = client
    # "refresh" is in ACTIONS but NOT in READ_ONLY_ACTIONS -> GET must 404, not run it.
    r = without_auth.get("/v1/plugins/crypto/actions/refresh")
    assert r.status_code == 404
    assert instance.refresh_calls == 0


def test_get_unknown_action_404(client):
    _, without_auth, _ = client
    r = without_auth.get("/v1/plugins/crypto/actions/delete_everything")
    assert r.status_code == 404


def test_get_unknown_plugin_404(client):
    _, without_auth, _ = client
    r = without_auth.get("/v1/plugins/nope/actions/get_price")
    assert r.status_code == 404


def test_get_missing_required_arg_400(client):
    _, without_auth, _ = client
    r = without_auth.get("/v1/plugins/crypto/actions/get_price")  # no ?coin=
    assert r.status_code == 400


def test_get_action_value_error_becomes_400(client):
    _, without_auth, _ = client
    r = without_auth.get(
        "/v1/plugins/crypto/actions/get_price", params={"coin": "boom"}
    )
    assert r.status_code == 400


def test_post_read_action_still_requires_jwt(client):
    _, without_auth, _ = client
    r = without_auth.post("/v1/plugins/crypto/actions/get_price", json={"coin": "btc"})
    assert r.status_code in (401, 403)


def test_post_read_action_works_with_jwt(client):
    with_auth, _, _ = client
    r = with_auth.post("/v1/plugins/crypto/actions/get_price", json={"coin": "btc"})
    assert r.status_code == 200
    assert r.json()["result"] == {"coin": "btc", "price": 42}


def test_post_mutating_action_works_with_jwt(client):
    with_auth, _, instance = client
    r = with_auth.post("/v1/plugins/crypto/actions/refresh", json={})
    assert r.status_code == 200
    assert instance.refresh_calls == 1


def test_post_action_generic_failure_does_not_leak_exception_text(client, monkeypatch):
    """#357: the generic `except Exception` catch-all used to return
    HTTPException(500, detail=f"Action failed: {e}") -- leaking the raw
    exception string. Now uses shared.errors.backend_http_error."""
    with_auth, _, instance = client
    secret_looking = "internal-db-password=hunter2"

    async def boom():
        raise RuntimeError(secret_looking)

    monkeypatch.setattr(instance, "refresh", boom)

    r = with_auth.post("/v1/plugins/crypto/actions/refresh", json={})

    assert r.status_code == 500
    assert secret_looking not in r.text
