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


def _load_ai_tools_module(plugins_path="/tmp"):
    saved_config = sys.modules.get("config")
    fake_config = ModuleType("config")
    fake_config.settings = SimpleNamespace(PLUGINS_PATH=plugins_path)
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


def _client(*, plugins_db, plugin_instances, plugins_path="/tmp"):
    mod = _load_ai_tools_module(plugins_path)
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


class _FailingInstance:
    async def analyze(self):
        raise RuntimeError("boom")


def test_analysis_500_on_analyze_exception():
    client = _client(
        plugins_db={"crypto": _FakePlugin(enabled=True)},
        plugin_instances={"crypto": _FailingInstance()},
    )
    r = client.get("/v1/plugins/crypto/analysis")
    assert r.status_code == 500
    assert "boom" in r.json()["detail"]


# --- GET /v1/plugins/ai/tools -----------------------------------------------


class _ModuleToolsInstance:
    """A module plugin declaring AI_TOOLS in code (no manifest on disk)."""

    def __init__(self, tools):
        self.AI_TOOLS = tools


def test_get_all_ai_tools_empty_when_no_plugins():
    client = _client(plugins_db={}, plugin_instances={})
    assert client.get("/v1/plugins/ai/tools").json() == {"tools": []}


def test_get_all_ai_tools_from_module_ai_tools_attribute():
    client = _client(
        plugins_db={"weather": _FakePlugin()},
        plugin_instances={
            "weather": _ModuleToolsInstance(
                [{"name": "get_weather", "description": "Current weather"}]
            )
        },
    )
    tools = client.get("/v1/plugins/ai/tools").json()["tools"]
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "get_weather"
    assert tools[0]["metadata"]["plugin"] == "weather"


def test_get_all_ai_tools_skips_a_plugin_with_no_live_instance():
    client = _client(
        plugins_db={"weather": _FakePlugin()},
        plugin_instances={},  # in plugins_db but never actually started
    )
    assert client.get("/v1/plugins/ai/tools").json() == {"tools": []}


class _RaisingToolsInstance:
    @property
    def AI_TOOLS(self):
        raise RuntimeError("boom")


def test_get_all_ai_tools_continues_after_a_per_plugin_exception():
    client = _client(
        plugins_db={"broken": _FakePlugin(), "weather": _FakePlugin()},
        plugin_instances={
            "broken": _RaisingToolsInstance(),
            "weather": _ModuleToolsInstance(
                [{"name": "get_weather", "description": "Current weather"}]
            ),
        },
    )
    tools = client.get("/v1/plugins/ai/tools").json()["tools"]
    assert len(tools) == 1
    assert tools[0]["function"]["name"] == "get_weather"


def test_get_all_ai_tools_combines_module_and_manifest_tools(tmp_path):
    plugin_dir = tmp_path / "hybrid"
    plugin_dir.mkdir()
    (plugin_dir / "manifest.yml").write_text(
        "ai_tools:\n  - name: manifest_tool\n    description: From the manifest\n"
    )
    client = _client(
        plugins_db={"hybrid": _FakePlugin()},
        plugin_instances={
            "hybrid": _ModuleToolsInstance(
                [{"name": "module_tool", "description": "From code"}]
            )
        },
        plugins_path=str(tmp_path),
    )
    tools = client.get("/v1/plugins/ai/tools").json()["tools"]
    names = {t["function"]["name"] for t in tools}
    assert names == {"module_tool", "manifest_tool"}


def test_tool_to_openai_skips_a_tool_with_no_name():
    client = _client(
        plugins_db={"weather": _FakePlugin()},
        plugin_instances={
            "weather": _ModuleToolsInstance([{"description": "no name here"}])
        },
    )
    assert client.get("/v1/plugins/ai/tools").json() == {"tools": []}


def test_tool_to_openai_maps_action_to_endpoint():
    client = _client(
        plugins_db={"weather": _FakePlugin()},
        plugin_instances={
            "weather": _ModuleToolsInstance(
                [{"name": "get_weather", "action": "current"}]
            )
        },
    )
    tool = client.get("/v1/plugins/ai/tools").json()["tools"][0]
    assert tool["metadata"]["endpoint"] == "/v1/plugins/weather/actions/current"
    assert tool["metadata"]["method"] == "POST"


def test_tool_to_openai_explicit_endpoint_overrides_action():
    client = _client(
        plugins_db={"weather": _FakePlugin()},
        plugin_instances={
            "weather": _ModuleToolsInstance(
                [
                    {
                        "name": "get_weather",
                        "action": "current",
                        "endpoint": "/custom",
                        "method": "GET",
                    }
                ]
            )
        },
    )
    tool = client.get("/v1/plugins/ai/tools").json()["tools"][0]
    assert tool["metadata"]["endpoint"] == "/v1/plugins/weather/custom"
    assert tool["metadata"]["method"] == "GET"


def test_tool_to_openai_defaults_parameters_and_endpoint_when_none_given():
    client = _client(
        plugins_db={"weather": _FakePlugin()},
        plugin_instances={"weather": _ModuleToolsInstance([{"name": "get_weather"}])},
    )
    tool = client.get("/v1/plugins/ai/tools").json()["tools"][0]
    assert tool["function"]["parameters"] == {
        "type": "object",
        "properties": {},
        "required": [],
    }
    # No action AND no endpoint -- must NOT synthesize "/actions/None".
    assert tool["metadata"]["endpoint"] == "/v1/plugins/weather"
