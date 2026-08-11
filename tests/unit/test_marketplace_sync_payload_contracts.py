"""Cross-service contract test: plugin-registry's marketplace_sync.py builds
JSON payloads for marketplace's own `POST /v1/marketplace/plugins`, but the
two services are never imported together in production (only ever talk over
HTTP) -- test_plugin_registry_marketplace_sync.py's own `_mkt_request` mock
never validates payload shape at all, it just always returns 201/200
regardless of what's sent. That's exactly how a real bug got through: found
live on hantal, `_resolve_or_create_bare_marketplace_plugin_id`'s bare-create
payload was missing the REQUIRED `author` field and got a real 422 from
marketplace, silently dropping the whole network->telegraf dependency edge
(the mocked unit tests all passed, since the mock accepts anything).

This validates the ACTUAL payload dicts plugin-registry's sync code builds
against marketplace's REAL `PluginCreate` Pydantic model, isolated-imported
from each service's own directory so their same-named `core`/`models`/
`config` packages never collide.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_PLUGIN_REGISTRY_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)
_MARKETPLACE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
)
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(service_dir: Path, module_path: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(service_dir))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return importlib.import_module(module_path)
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.mark.asyncio
async def test_bare_dependency_target_create_payload_satisfies_plugin_create():
    marketplace_sync = _isolated_import(_PLUGIN_REGISTRY_DIR, "core.marketplace_sync")
    plugin_model = _isolated_import(_MARKETPLACE_DIR, "models.plugin")

    captured = {}

    async def fake_request(method, url, **kwargs):
        if method == "GET":  # search -- not found, forces the create path
            return _FakeResponse(200, {"plugins": []})
        captured["json"] = kwargs.get("json")
        return _FakeResponse(201, {"id": "some-id"})

    marketplace_sync._mkt_request = AsyncMock(side_effect=fake_request)

    await marketplace_sync._resolve_or_create_bare_marketplace_plugin_id("telegraf")

    assert captured.get("json"), "the create path was never reached"
    # Must not raise -- this is exactly the payload marketplace's real
    # endpoint validates against.
    plugin_model.PluginCreate(**captured["json"])
