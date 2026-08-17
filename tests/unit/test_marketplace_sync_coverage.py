"""Unit tests filling marketplace_sync.py's remaining coverage gaps (71%).

The sibling suites already cover the happy-path metadata pass-through,
dependency-graph recording, reconciliation, and required_tier passthrough.
This adds everything else: _mkt_request's own retry-then-succeed and
retries-exhausted paths, _to_marketplace_tool's nested-JSON-Schema-to-flat
conversion (+ action-derived endpoint), manifest.yml/json file loading,
sync_plugin_ai_tools' plugin-id-not-obtained early return and the ai/sync
non-200 + outer-exception branches, _resolve_or_create_bare_marketplace_
plugin_id's create-failure branch, _sync_plugin_dependencies' dep-not-found
skip + non-200 + exception branches, _reconcile_marketplace_plugin's
failure + exception branches, repository_url inclusion, and
get_or_create_marketplace_plugin's create-failure + outer-exception
branches.

Same _fresh_import pattern as the sibling suite (marketplace_sync.py does
`from core.state import logger`, needing a real `core` package on sys.path).
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
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
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")

    import importlib

    return importlib.import_module(module_path)


marketplace_sync = _fresh_import("core.marketplace_sync")


class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or str(self._payload)

    def json(self):
        return self._payload


# --- _mkt_request: retry/backoff behaviour ------------------------------------


class _FakeAsyncClient:
    def __init__(self, outcome):
        self._outcome = outcome

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method, url, **kwargs):
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return self._outcome


def _client_factory(outcomes):
    it = iter(outcomes)

    def factory(*a, **k):
        return _FakeAsyncClient(next(it))

    return factory


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    async def _fast_sleep(*a, **k):
        return None

    monkeypatch.setattr(marketplace_sync.asyncio, "sleep", _fast_sleep)


@pytest.mark.asyncio
async def test_mkt_request_succeeds_immediately_with_no_retry(monkeypatch):
    ok = _FakeResponse(200, {"ok": True})
    monkeypatch.setattr(marketplace_sync.httpx, "AsyncClient", _client_factory([ok]))

    result = await marketplace_sync._mkt_request("GET", "http://mkt/x")

    assert result is ok


@pytest.mark.asyncio
async def test_mkt_request_retries_connect_errors_then_succeeds(monkeypatch):
    ok = _FakeResponse(200, {"ok": True})
    outcomes = [
        httpx.ConnectError("not ready", request=None),
        httpx.ConnectTimeout("timeout", request=None),
        ok,
    ]
    monkeypatch.setattr(
        marketplace_sync.httpx, "AsyncClient", _client_factory(outcomes)
    )

    result = await marketplace_sync._mkt_request("GET", "http://mkt/x")

    assert result is ok


@pytest.mark.asyncio
async def test_mkt_request_raises_the_last_error_when_retries_exhausted(monkeypatch):
    last = httpx.ConnectError("final failure", request=None)
    outcomes = [
        httpx.ConnectError("attempt 1", request=None),
        httpx.ConnectError("attempt 2", request=None),
        httpx.ConnectError("attempt 3", request=None),
        last,
    ]
    monkeypatch.setattr(
        marketplace_sync.httpx, "AsyncClient", _client_factory(outcomes)
    )

    with pytest.raises(httpx.ConnectError) as exc:
        await marketplace_sync._mkt_request("GET", "http://mkt/x")

    assert exc.value is last


# --- _to_marketplace_tool: nested JSON-Schema flattening ---------------------


def test_to_marketplace_tool_flattens_nested_json_schema_parameters():
    tool = {
        "name": "get_price",
        "action": "get_price",
        "parameters": {
            "type": "object",
            "properties": {
                "coin": {"type": "string", "description": "Coin symbol"},
                "currency": {"type": "string"},
            },
            "required": ["coin"],
        },
    }

    out = marketplace_sync._to_marketplace_tool(tool)

    assert out["parameters"]["coin"]["required"] is True
    assert out["parameters"]["currency"]["required"] is False
    assert out["parameters"]["coin"]["description"] == "Coin symbol"
    assert out["endpoint"] == "/actions/get_price"
    assert out["type"] == "action"


def test_to_marketplace_tool_passes_through_already_flat_parameters():
    tool = {"name": "lookup", "parameters": {"target": {"type": "string"}}}

    out = marketplace_sync._to_marketplace_tool(tool)

    assert out["parameters"] == {"target": {"type": "string"}}
    assert out["type"] == "analysis"
    assert "endpoint" not in out


# --- manifest.yml / manifest.json loading -------------------------------------


@pytest.mark.asyncio
async def test_sync_reads_a_yaml_manifest_from_disk(tmp_path, monkeypatch):
    (tmp_path / "manifest.yml").write_text(
        "name: weather\nversion: 1.0.0\nai_tools:\n  - name: get_forecast\n",
        encoding="utf-8",
    )
    captured = {}

    async def fake_get_or_create(plugin_name, manifest):
        captured["manifest"] = manifest
        return "plugin-id"

    monkeypatch.setattr(
        marketplace_sync, "get_or_create_marketplace_plugin", fake_get_or_create
    )
    monkeypatch.setattr(
        marketplace_sync,
        "_mkt_request",
        AsyncMock(return_value=_FakeResponse(200, {"tools_imported": 1})),
    )

    await marketplace_sync.sync_plugin_ai_tools("weather", tmp_path)

    assert captured["manifest"]["name"] == "weather"
    assert len(captured["manifest"]["ai_tools"]) == 1


@pytest.mark.asyncio
async def test_sync_reads_a_json_manifest_from_disk(tmp_path, monkeypatch):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"name": "crypto", "ai_tools": [{"name": "get_price"}]}),
        encoding="utf-8",
    )
    captured = {}

    async def fake_get_or_create(plugin_name, manifest):
        captured["manifest"] = manifest
        return "plugin-id"

    monkeypatch.setattr(
        marketplace_sync, "get_or_create_marketplace_plugin", fake_get_or_create
    )
    monkeypatch.setattr(
        marketplace_sync,
        "_mkt_request",
        AsyncMock(return_value=_FakeResponse(200, {"tools_imported": 1})),
    )

    await marketplace_sync.sync_plugin_ai_tools("crypto", tmp_path)

    assert captured["manifest"]["name"] == "crypto"


# --- sync_plugin_ai_tools: plugin-id failure / ai-sync failure / exception ---


@pytest.mark.asyncio
async def test_sync_returns_early_when_plugin_id_could_not_be_obtained(
    tmp_path, monkeypatch
):
    calls = {"n": 0}

    async def fake_get_or_create(plugin_name, manifest):
        calls["n"] += 1
        return None

    mkt_request = AsyncMock()
    monkeypatch.setattr(
        marketplace_sync, "get_or_create_marketplace_plugin", fake_get_or_create
    )
    monkeypatch.setattr(marketplace_sync, "_mkt_request", mkt_request)

    await marketplace_sync.sync_plugin_ai_tools(
        "weather", tmp_path, module_ai_tools=[{"name": "get_forecast"}]
    )

    assert calls["n"] == 1
    mkt_request.assert_not_awaited()  # never reached the /ai/sync call


@pytest.mark.asyncio
async def test_sync_logs_a_warning_on_ai_sync_non_200(tmp_path, monkeypatch):
    monkeypatch.setattr(
        marketplace_sync,
        "get_or_create_marketplace_plugin",
        AsyncMock(return_value="plugin-id"),
    )
    monkeypatch.setattr(
        marketplace_sync,
        "_mkt_request",
        AsyncMock(return_value=_FakeResponse(500, text="boom")),
    )

    # Must not raise -- sync_plugin_ai_tools swallows this into a warning log.
    await marketplace_sync.sync_plugin_ai_tools(
        "weather", tmp_path, module_ai_tools=[{"name": "get_forecast"}]
    )


@pytest.mark.asyncio
async def test_sync_swallows_an_unexpected_exception(tmp_path, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(marketplace_sync, "get_or_create_marketplace_plugin", boom)

    # Must not raise -- the whole function body is wrapped in try/except.
    await marketplace_sync.sync_plugin_ai_tools(
        "weather", tmp_path, module_ai_tools=[{"name": "get_forecast"}]
    )


# --- _resolve_or_create_bare_marketplace_plugin_id: create failure -----------


@pytest.mark.asyncio
async def test_resolve_or_create_bare_plugin_returns_none_on_create_failure(
    monkeypatch,
):
    async def fake_request(method, url, **kwargs):
        if method == "GET":
            return _FakeResponse(200, {"plugins": []})
        return _FakeResponse(500, text="create failed")

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )

    result = await marketplace_sync._resolve_or_create_bare_marketplace_plugin_id(
        "telegraf"
    )

    assert result is None


# --- _sync_plugin_dependencies: skip / failure / exception branches ----------


@pytest.mark.asyncio
async def test_sync_plugin_dependencies_skips_when_dep_id_not_resolved(monkeypatch):
    async def fake_resolve(dep_name):
        return None

    mkt_request = AsyncMock()
    monkeypatch.setattr(
        marketplace_sync, "_resolve_or_create_bare_marketplace_plugin_id", fake_resolve
    )
    monkeypatch.setattr(marketplace_sync, "_mkt_request", mkt_request)

    await marketplace_sync._sync_plugin_dependencies(
        "plugin-1", "network", ["telegraf"]
    )

    mkt_request.assert_not_awaited()  # never reached the dependency-edge POST


@pytest.mark.asyncio
async def test_sync_plugin_dependencies_logs_warning_on_non_200(monkeypatch):
    async def fake_resolve(dep_name):
        return "dep-id"

    monkeypatch.setattr(
        marketplace_sync, "_resolve_or_create_bare_marketplace_plugin_id", fake_resolve
    )
    monkeypatch.setattr(
        marketplace_sync,
        "_mkt_request",
        AsyncMock(return_value=_FakeResponse(500, text="boom")),
    )

    # Must not raise.
    await marketplace_sync._sync_plugin_dependencies(
        "plugin-1", "network", ["telegraf"]
    )


@pytest.mark.asyncio
async def test_sync_plugin_dependencies_one_failing_edge_does_not_block_the_rest(
    monkeypatch,
):
    resolved = []

    async def fake_resolve(dep_name):
        resolved.append(dep_name)
        if dep_name == "telegraf":
            raise RuntimeError("resolution exploded")
        return "dep-id-2"

    monkeypatch.setattr(
        marketplace_sync, "_resolve_or_create_bare_marketplace_plugin_id", fake_resolve
    )
    monkeypatch.setattr(
        marketplace_sync,
        "_mkt_request",
        AsyncMock(return_value=_FakeResponse(200, {})),
    )

    await marketplace_sync._sync_plugin_dependencies(
        "plugin-1", "network", ["telegraf", "weather"]
    )

    assert resolved == ["telegraf", "weather"]  # both attempted


# --- _reconcile_marketplace_plugin: failure + exception branches ------------


@pytest.mark.asyncio
async def test_reconcile_marketplace_plugin_logs_warning_on_non_200(monkeypatch):
    monkeypatch.setattr(
        marketplace_sync,
        "_mkt_request",
        AsyncMock(return_value=_FakeResponse(500, text="boom")),
    )

    # Must not raise.
    await marketplace_sync._reconcile_marketplace_plugin(
        "plugin-1", "weather", "Weather", "desc", "Author", []
    )


@pytest.mark.asyncio
async def test_reconcile_marketplace_plugin_swallows_an_exception(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(marketplace_sync, "_mkt_request", boom)

    # Must not raise.
    await marketplace_sync._reconcile_marketplace_plugin(
        "plugin-1", "weather", "Weather", "desc", "Author", []
    )


# --- get_or_create_marketplace_plugin: repository_url + failure branches ----


@pytest.mark.asyncio
async def test_get_or_create_includes_repository_url_when_present(monkeypatch):
    captured = {}

    async def fake_request(method, url, **kwargs):
        if method == "GET":
            return _FakeResponse(200, {"plugins": []})
        captured["json"] = kwargs.get("json")
        return _FakeResponse(201, {"id": "new-id"})

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )

    result = await marketplace_sync.get_or_create_marketplace_plugin(
        "weather", {"description": "desc", "repository": "https://github.com/x/y"}
    )

    assert result == "new-id"
    assert captured["json"]["repository_url"] == "https://github.com/x/y"


@pytest.mark.asyncio
async def test_get_or_create_omits_repository_url_when_blank(monkeypatch):
    captured = {}

    async def fake_request(method, url, **kwargs):
        if method == "GET":
            return _FakeResponse(200, {"plugins": []})
        captured["json"] = kwargs.get("json")
        return _FakeResponse(201, {"id": "new-id"})

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )

    await marketplace_sync.get_or_create_marketplace_plugin(
        "weather", {"description": "desc", "repository": "   "}
    )

    assert "repository_url" not in captured["json"]


@pytest.mark.asyncio
async def test_get_or_create_returns_none_on_create_failure(monkeypatch):
    async def fake_request(method, url, **kwargs):
        if method == "GET":
            return _FakeResponse(200, {"plugins": []})
        return _FakeResponse(500, text="create failed")

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )

    result = await marketplace_sync.get_or_create_marketplace_plugin(
        "weather", {"description": "desc"}
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_or_create_returns_none_and_logs_on_unexpected_exception(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(marketplace_sync, "_mkt_request", boom)

    result = await marketplace_sync.get_or_create_marketplace_plugin(
        "weather", {"description": "desc"}
    )

    assert result is None
