"""Unit tests for the plugin-registry generic /analysis endpoint (#147 C9 tail).

The redesign dropped the per-plugin hardcoded reshaping (crypto/news/weather/
network/tefas branches) that coupled the registry to each first-party plugin's
output schema. These lock the new contract: the registry returns the plugin's
``analyze()`` output **verbatim** (no reshaping, no plugin-specific query params)
and reports 404 / 403 / 503 for missing / disabled / not-running plugins.

The route is built by a factory with injected state (like the bundles route), so
it loads by path. ``ai_tools`` does ``from config import settings`` at module top,
so a fake ``config`` is injected and restored to avoid poisoning another service's
equally named top-level ``config`` in the shared pytest process (the #142 gotcha).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "plugin-registry"
    / "routes"
    / "ai_tools.py"
)


def _load_ai_tools_module():
    saved_config = sys.modules.get("config")
    fake_config = ModuleType("config")
    fake_config.settings = SimpleNamespace(PLUGINS_PATH="/tmp")
    sys.modules["config"] = fake_config
    try:
        spec = importlib.util.spec_from_file_location("registry_ai_tools_route", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


class _FakePlugin:
    def __init__(self, enabled=True):
        self.enabled = enabled


class _FakeInstance:
    def __init__(self, result):
        self._result = result

    async def analyze(self):
        return self._result


_NOOP_LOGGER = SimpleNamespace(
    error=lambda *a, **k: None,
    info=lambda *a, **k: None,
    warning=lambda *a, **k: None,
)

# A plugin-specific shape the OLD code would have reshaped for crypto — kept whole
# here to prove the registry passes analyze() through untouched.
_ANALYZE_RESULT = {
    "metrics": {"BTC": {"price": 42000, "change": 1.2}},
    "insights": "bull",
    "custom_field": ["a", "b"],
}


def _client(*, plugins_db, plugin_instances):
    mod = _load_ai_tools_module()
    app = FastAPI()
    app.include_router(
        mod.build_ai_tools_router(
            plugins_db=plugins_db,
            plugin_instances=plugin_instances,
            logger=_NOOP_LOGGER,
        )
    )
    return TestClient(app, raise_server_exceptions=True)


def test_analysis_returns_analyze_output_verbatim():
    client = _client(
        plugins_db={"crypto": _FakePlugin(enabled=True)},
        plugin_instances={"crypto": _FakeInstance(_ANALYZE_RESULT)},
    )
    # Even with a plugin-specific query param the old code honoured, the result is
    # the full analyze() dict — no reshaping, param ignored.
    r = client.get("/v1/plugins/crypto/analysis?symbol=BTC")
    assert r.status_code == 200
    assert r.json() == _ANALYZE_RESULT


def test_analysis_unknown_plugin_404():
    client = _client(plugins_db={}, plugin_instances={})
    assert client.get("/v1/plugins/nope/analysis").status_code == 404


def test_analysis_disabled_plugin_403():
    client = _client(
        plugins_db={"crypto": _FakePlugin(enabled=False)},
        plugin_instances={"crypto": _FakeInstance(_ANALYZE_RESULT)},
    )
    assert client.get("/v1/plugins/crypto/analysis").status_code == 403


def test_analysis_not_running_plugin_503():
    client = _client(
        plugins_db={"crypto": _FakePlugin(enabled=True)},
        plugin_instances={},  # enabled but no live instance
    )
    assert client.get("/v1/plugins/crypto/analysis").status_code == 503
