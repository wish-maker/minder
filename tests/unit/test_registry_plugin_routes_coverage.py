"""Unit tests filling routes/plugins.py's remaining coverage gaps (57%).

Existing suites (test_registry_plugin_{read,write}_actions.py,
test_registry_plugin_uninstall_cleanup.py, test_plugin_registry_webhook_persistence.py,
test_plugin_registry_proxy_error_handling.py) already cover enable/disable's
happy-path persist-before-mutate contract, uninstall's cleanup, install's
webhook-failure contract, and the read-action route's core behavior. This adds
everything still untouched: list_plugins pagination, get_plugin, install's
parse/validation/conflict branches, the generic webhook route, enable/disable's
plugin_instances status sync + 404s, reload_plugin_webhook end-to-end,
get_plugin_health, trigger_plugin_collection, invoke_plugin_{read_action,action}'s
remaining error branches, and the config GET/PUT pair.

Same `_fresh_import` + fake-`schemas.validator` pattern as the sibling suites
(routes/plugins.py needs the real plugin-registry package tree on sys.path, and
schemas.validator pulls in jsonschema, irrelevant here).
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


def _fresh_import(module_path: str, *, validate_manifest=None):
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
    fake_validator.validate_manifest = validate_manifest or (lambda *a, **k: (True, []))
    fake_schemas.validator = fake_validator
    sys.modules["schemas"] = fake_schemas
    sys.modules["schemas.validator"] = fake_validator

    import importlib

    return importlib.import_module(module_path)


async def _async_noop(*a, **k):
    return None


async def _async_empty_dict(*a, **k):
    return {}


class _NoopLogger:
    def info(self, *a, **k):
        pass

    def error(self, *a, **k):
        pass


class _Plugin:
    """Stand-in for models.PluginInfo -- these routes only read/mutate .status
    and .health_status/.last_health_check, never construct or type-check it."""

    def __init__(
        self, status="registered", health_status="unknown", last_health_check=None
    ):
        self.status = status
        self.health_status = health_status
        self.last_health_check = last_health_check


def _build(
    *,
    plugins_db=None,
    plugin_instances=None,
    plugin_manifests=None,
    webhook_routes=None,
    redis_client=None,
    update_plugin_in_database=None,
    delete_plugin_from_database=None,
    load_plugin_config=None,
    save_plugin_config=None,
    register_plugin_webhook=None,
    handle_webhook_request=None,
    validate_manifest=None,
    auth=True,
):
    routes_plugins = _fresh_import(
        "routes.plugins", validate_manifest=validate_manifest
    )
    app = FastAPI()
    app.include_router(
        routes_plugins.build_plugins_router(
            plugins_db=plugins_db if plugins_db is not None else {},
            plugin_instances=plugin_instances if plugin_instances is not None else {},
            plugin_manifests=plugin_manifests if plugin_manifests is not None else {},
            webhook_routes=webhook_routes if webhook_routes is not None else {},
            redis_client=redis_client,
            update_plugin_in_database=update_plugin_in_database or _async_noop,
            delete_plugin_from_database=delete_plugin_from_database or _async_noop,
            load_plugin_config=load_plugin_config or _async_empty_dict,
            save_plugin_config=save_plugin_config or _async_noop,
            register_plugin_webhook=register_plugin_webhook or _async_noop,
            handle_webhook_request=handle_webhook_request or _async_noop,
            logger=_NoopLogger(),
        )
    )
    if auth:
        app.dependency_overrides[routes_plugins.get_current_user] = lambda: {
            "username": "tester",
            "role": "admin",
        }
    return TestClient(app, raise_server_exceptions=False)


# --- list_plugins / get_plugin -----------------------------------------------


def test_list_plugins_paginates():
    plugins_db = {f"p{i}": _Plugin() for i in range(3)}
    client = _build(plugins_db=plugins_db)

    r = client.get("/v1/plugins", params={"limit": 2, "offset": 0})

    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0


def test_get_plugin_found():
    plugin = _Plugin()
    client = _build(plugins_db={"weather": plugin})

    r = client.get("/v1/plugins/weather")

    assert r.status_code == 200


def test_get_plugin_404():
    client = _build(plugins_db={})

    r = client.get("/v1/plugins/nope")

    assert r.status_code == 404


# --- install_plugin's remaining branches --------------------------------------


def test_install_plugin_bad_body_400():
    client = _build()

    r = client.post(
        "/v1/plugins/install",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 400


def test_install_plugin_invalid_manifest_422():
    client = _build(validate_manifest=lambda m: (False, ["missing spec"]))

    r = client.post(
        "/v1/plugins/install",
        content=json.dumps({"metadata": {"name": "weather"}}),
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 422
    assert r.json()["detail"] == ["missing spec"]


def test_install_plugin_missing_name_400():
    client = _build()

    r = client.post(
        "/v1/plugins/install",
        content=json.dumps({"metadata": {}}),
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 400


def test_install_plugin_already_installed_409():
    client = _build(plugins_db={"weather": _Plugin()})

    r = client.post(
        "/v1/plugins/install",
        content=json.dumps({"metadata": {"name": "weather"}}),
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 409


def test_install_plugin_db_failure_500():
    async def boom(*a, **k):
        raise RuntimeError("db down")

    client = _build(update_plugin_in_database=boom)

    r = client.post(
        "/v1/plugins/install",
        content=json.dumps({"metadata": {"name": "weather"}}),
        headers={"content-type": "application/json"},
    )

    assert r.status_code == 500


# --- uninstall_plugin's remaining branches --------------------------------------


def test_uninstall_plugin_404():
    client = _build(plugins_db={})
    r = client.delete("/v1/plugins/nope")
    assert r.status_code == 404


def test_uninstall_plugin_shuts_down_running_instance():
    class _Instance:
        def __init__(self):
            self.shut_down = False

        async def shutdown(self):
            self.shut_down = True

    class _FakeRedis:
        def delete(self, *a, **k):
            pass

    instance = _Instance()
    plugin_instances = {"weather": instance}
    client = _build(
        plugins_db={"weather": _Plugin()},
        plugin_instances=plugin_instances,
        redis_client=_FakeRedis(),
    )

    r = client.delete("/v1/plugins/weather")

    assert r.status_code == 200
    assert instance.shut_down is True
    assert "weather" not in plugin_instances


# --- generic webhook route ------------------------------------------------------


def test_handle_webhook_route_forwards_to_injected_handler():
    calls = []

    async def fake_handler(path, request):
        calls.append(path)
        return {"ok": True}

    client = _build(handle_webhook_request=fake_handler)

    r = client.post("/webhook/weather/notify")

    assert r.status_code == 200
    assert calls == ["/webhook/weather/notify"]


# --- enable/disable: 404s + plugin_instances status sync ----------------------


def test_enable_plugin_404():
    client = _build(plugins_db={})
    r = client.post("/v1/plugins/nope/enable")
    assert r.status_code == 404


def test_disable_plugin_404():
    client = _build(plugins_db={})
    r = client.post("/v1/plugins/nope/disable")
    assert r.status_code == 404


def test_enable_plugin_syncs_running_instance_status():
    plugin = _Plugin("registered")
    instance = _Plugin(status="idle")  # only needs a mutable .status attribute

    client = _build(
        plugins_db={"weather": plugin},
        plugin_instances={"weather": instance},
    )

    r = client.post("/v1/plugins/weather/enable")

    assert r.status_code == 200
    assert instance.status == "ready"


def test_disable_plugin_syncs_running_instance_status():
    plugin = _Plugin("enabled")
    instance = _Plugin(status="ready")

    client = _build(
        plugins_db={"weather": plugin},
        plugin_instances={"weather": instance},
    )

    r = client.post("/v1/plugins/weather/disable")

    assert r.status_code == 200
    assert instance.status == "registered"


# --- reload_plugin_webhook -----------------------------------------------------


def _manifest(name="weather"):
    return {
        "metadata": {"name": name, "version": "1.0.0"},
        "spec": {"trigger": {"webhook": {"path": "/weather"}}},
    }


def test_reload_plugin_webhook_bad_body_400():
    client = _build(plugins_db={"weather": _Plugin()})
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_reload_plugin_webhook_invalid_manifest_422():
    client = _build(
        plugins_db={"weather": _Plugin()},
        validate_manifest=lambda m: (False, ["bad"]),
    )
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=json.dumps(_manifest()),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 422


def test_reload_plugin_webhook_missing_name_400():
    client = _build(plugins_db={"weather": _Plugin()})
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=json.dumps({"metadata": {}, "spec": {}}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_reload_plugin_webhook_unknown_plugin_404():
    client = _build(plugins_db={})
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=json.dumps(_manifest()),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 404


def test_reload_plugin_webhook_registration_failure_500():
    async def boom(name, manifest):
        raise RuntimeError("route conflict")

    client = _build(plugins_db={"weather": _Plugin()}, register_plugin_webhook=boom)
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=json.dumps(_manifest()),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 500


def test_reload_plugin_webhook_success():
    webhook_routes = {"/old/path": "weather"}

    async def fake_register(name, manifest):
        return None

    client = _build(
        plugins_db={"weather": _Plugin()},
        webhook_routes=webhook_routes,
        register_plugin_webhook=fake_register,
    )
    r = client.post(
        "/v1/plugins/reload-webhook",
        content=json.dumps(_manifest()),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["webhook_path"] == "/webhook/weather"
    assert body["registered_routes"] == ["/old/path"]


# --- get_plugin_health ----------------------------------------------------------


def test_get_plugin_health_404():
    client = _build(plugins_db={})
    r = client.get("/v1/plugins/nope/health")
    assert r.status_code == 404


def test_get_plugin_health_no_running_instance():
    client = _build(
        plugins_db={"weather": _Plugin(health_status="degraded", last_health_check="t")}
    )
    r = client.get("/v1/plugins/weather/health")
    assert r.status_code == 200
    body = r.json()
    assert body["health_status"] == "degraded"
    assert body["message"] == "Plugin instance not available"


def test_get_plugin_health_delegates_to_running_instance():
    class _Instance:
        async def health_check(self):
            return {"status": "ok"}

    client = _build(
        plugins_db={"weather": _Plugin()},
        plugin_instances={"weather": _Instance()},
    )
    r = client.get("/v1/plugins/weather/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# --- trigger_plugin_collection --------------------------------------------------


def test_trigger_collection_404_unknown_plugin():
    client = _build(plugins_db={})
    r = client.post("/v1/plugins/nope/collect")
    assert r.status_code == 404


def test_trigger_collection_400_when_not_enabled():
    client = _build(plugins_db={"weather": _Plugin(status="disabled")})
    r = client.post("/v1/plugins/weather/collect")
    assert r.status_code == 400


def test_trigger_collection_500_when_instance_missing():
    client = _build(plugins_db={"weather": _Plugin(status="enabled")})
    r = client.post("/v1/plugins/weather/collect")
    assert r.status_code == 500


def test_trigger_collection_success_schedules_background_task():
    class _Instance:
        def __init__(self):
            self.collected = 0

        async def collect_data(self):
            self.collected += 1

    instance = _Instance()
    client = _build(
        plugins_db={"weather": _Plugin(status="enabled")},
        plugin_instances={"weather": instance},
    )
    r = client.post("/v1/plugins/weather/collect")
    assert r.status_code == 200
    assert r.json()["status"] == "collecting"
    assert instance.collected == 1  # BackgroundTasks run synchronously in TestClient


# --- invoke_plugin_read_action's remaining branches -----------------------------


class _ActionPlugin:
    ACTIONS = frozenset({"refresh", "get_price", "awaitable_action"})
    READ_ONLY_ACTIONS = frozenset({"get_price", "awaitable_action"})

    def __init__(self):
        self.refresh_calls = 0

    async def refresh(self):
        self.refresh_calls += 1
        return {"refreshed": True}

    def get_price(self, coin: str):
        return {"coin": coin}

    async def awaitable_action(self):
        return {"async": True}


def test_get_read_action_bad_arguments_400():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    # get_price requires `coin`; pass an unexpected kwarg instead so bind() raises.
    r = client.get("/v1/plugins/crypto/actions/get_price", params={"unexpected": "x"})
    assert r.status_code == 400


def test_get_read_action_awaits_coroutine_result():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    r = client.get("/v1/plugins/crypto/actions/awaitable_action")
    assert r.status_code == 200
    assert r.json()["result"] == {"async": True}


def test_get_read_action_reraises_http_exception_from_method_unmodified():
    from fastapi import HTTPException

    class _Picky:
        ACTIONS = frozenset({"get_price"})
        READ_ONLY_ACTIONS = frozenset({"get_price"})

        def get_price(self, coin: str):
            raise HTTPException(status_code=418, detail="I'm a teapot")

    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _Picky()}
    )
    r = client.get("/v1/plugins/crypto/actions/get_price", params={"coin": "btc"})
    assert r.status_code == 418
    assert r.json()["detail"] == "I'm a teapot"


def test_get_read_action_generic_exception_masked_500():
    class _Boom:
        ACTIONS = frozenset({"get_price"})
        READ_ONLY_ACTIONS = frozenset({"get_price"})

        def get_price(self, coin: str):
            raise RuntimeError("secret-conn-string=hunter2")

    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _Boom()}
    )
    r = client.get("/v1/plugins/crypto/actions/get_price", params={"coin": "btc"})
    assert r.status_code == 500
    assert "hunter2" not in r.text


# --- invoke_plugin_action's remaining branches ----------------------------------


def test_post_action_unknown_plugin_404():
    client = _build(plugins_db={})
    r = client.post("/v1/plugins/nope/actions/refresh", json={})
    assert r.status_code == 404


def test_post_action_unknown_action_404():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    r = client.post("/v1/plugins/crypto/actions/delete_everything", json={})
    assert r.status_code == 404


def test_post_action_bad_json_body_400():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    r = client.post(
        "/v1/plugins/crypto/actions/refresh",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_post_action_non_object_body_400():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    r = client.post(
        "/v1/plugins/crypto/actions/refresh",
        content=json.dumps([1, 2, 3]),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_post_action_bad_arguments_400():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    r = client.post("/v1/plugins/crypto/actions/get_price", json={"unexpected": "x"})
    assert r.status_code == 400


def test_post_action_value_error_400():
    class _Boom:
        ACTIONS = frozenset({"get_price"})

        def get_price(self, coin: str):
            raise ValueError("unknown coin")

    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _Boom()}
    )
    r = client.post("/v1/plugins/crypto/actions/get_price", json={"coin": "boom"})
    assert r.status_code == 400


def test_post_action_awaits_coroutine_result():
    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _ActionPlugin()}
    )
    r = client.post("/v1/plugins/crypto/actions/awaitable_action", json={})
    assert r.status_code == 200
    assert r.json()["result"] == {"async": True}


def test_post_action_reraises_http_exception_from_method_unmodified():
    from fastapi import HTTPException

    class _Picky:
        ACTIONS = frozenset({"get_price"})

        def get_price(self, coin: str):
            raise HTTPException(status_code=418, detail="I'm a teapot")

    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _Picky()}
    )
    r = client.post("/v1/plugins/crypto/actions/get_price", json={"coin": "btc"})
    assert r.status_code == 418
    assert r.json()["detail"] == "I'm a teapot"


def test_post_action_generic_exception_masked_500():
    class _Boom:
        ACTIONS = frozenset({"get_price"})

        def get_price(self, coin: str):
            raise RuntimeError("secret-conn-string=hunter2")

    client = _build(
        plugins_db={"crypto": _Plugin()}, plugin_instances={"crypto": _Boom()}
    )
    r = client.post("/v1/plugins/crypto/actions/get_price", json={"coin": "btc"})
    assert r.status_code == 500
    assert "hunter2" not in r.text


# --- get_plugin_config / update_plugin_config -----------------------------------


class _ConfigurablePlugin:
    CONFIG_SCHEMA = [
        {"key": "THRESHOLD", "type": "int", "default": 5},
        {"key": "API_KEY", "type": "string", "secret": True, "default": ""},
    ]

    def __init__(self):
        self.applied = None

    def apply_config(self, cfg):
        self.applied = cfg


class _UnconfigurablePlugin:
    pass


def test_get_plugin_config_404_no_running_instance():
    client = _build(plugin_instances={})
    r = client.get("/v1/plugins/weather/config")
    assert r.status_code == 404


def test_get_plugin_config_not_configurable():
    client = _build(plugin_instances={"weather": _UnconfigurablePlugin()})
    r = client.get("/v1/plugins/weather/config")
    assert r.status_code == 200
    body = r.json()
    assert body["configurable"] is False
    assert body["schema"] == []


def test_get_plugin_config_returns_masked_effective_values():
    async def fake_load(name):
        return {"API_KEY": "sekrit"}

    client = _build(
        plugin_instances={"weather": _ConfigurablePlugin()},
        load_plugin_config=fake_load,
    )
    r = client.get("/v1/plugins/weather/config")
    assert r.status_code == 200
    body = r.json()
    assert body["configurable"] is True
    assert body["values"]["THRESHOLD"] == 5
    assert body["values"]["API_KEY"] == "***"


def test_update_plugin_config_404_no_running_instance():
    client = _build(plugin_instances={})
    r = client.put(
        "/v1/plugins/weather/config",
        content=json.dumps({"THRESHOLD": 10}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 404


def test_update_plugin_config_400_not_configurable():
    client = _build(plugin_instances={"weather": _UnconfigurablePlugin()})
    r = client.put(
        "/v1/plugins/weather/config",
        content=json.dumps({"THRESHOLD": 10}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_update_plugin_config_bad_json_400():
    client = _build(plugin_instances={"weather": _ConfigurablePlugin()})
    r = client.put(
        "/v1/plugins/weather/config",
        content=b"{not json",
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_update_plugin_config_unknown_key_400():
    client = _build(plugin_instances={"weather": _ConfigurablePlugin()})
    r = client.put(
        "/v1/plugins/weather/config",
        content=json.dumps({"NOT_A_FIELD": 1}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 400


def test_update_plugin_config_success_persists_and_applies():
    instance = _ConfigurablePlugin()
    saved = {}

    async def fake_load(name):
        return {}

    async def fake_save(name, cfg):
        saved.update(cfg)

    client = _build(
        plugin_instances={"weather": instance},
        load_plugin_config=fake_load,
        save_plugin_config=fake_save,
    )
    r = client.put(
        "/v1/plugins/weather/config",
        content=json.dumps({"THRESHOLD": 42}),
        headers={"content-type": "application/json"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == ["THRESHOLD"]
    assert body["values"]["THRESHOLD"] == 42
    assert saved == {"THRESHOLD": 42}
    assert instance.applied == {"THRESHOLD": 42, "API_KEY": ""}
