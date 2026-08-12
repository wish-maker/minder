"""Unit tests for module-plugin metadata pass-through in marketplace sync.

Found live on the Pi: `GET /v1/marketplace/plugins` showed every first-party
module plugin (news, weather, crypto, tefas, network) synced with an EMPTY
description and author "Unknown" -- `sync_plugin_ai_tools` synthesised a
throwaway manifest (`{"name": ..., "version": "1.0.0", "description": ""}`)
for module plugins instead of using the plugin's real `PluginMetadata`, even
though the caller (plugin_loader.py) already has `metadata.description` /
`metadata.author` in hand a few lines above the call site. These lock the fix:
the synthesised manifest must carry whatever description/author the caller
passes in.

Loaded via sys.path + a stale-cache clear (marketplace_sync.py does `from
core.state import logger`, a package-qualified import needing a real `core`
package on sys.path) -- same pattern as
test_plugin_registry_webhook_persistence.py.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

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


marketplace_sync = _fresh_import("core.marketplace_sync")


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(payload)

    def json(self):
        return self._payload


@pytest.fixture
def captured_requests(monkeypatch):
    """Stub _mkt_request: no plugin found by search, then a 201-create."""
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":  # the "search for existing plugin" call
            return _FakeResponse(200, {"plugins": []})
        if url.endswith("/v1/marketplace/plugins"):  # create
            return _FakeResponse(201, {"id": "fake-plugin-id"})
        return _FakeResponse(200, {"tools_imported": 1})  # /ai/sync

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )
    return calls


@pytest.mark.asyncio
async def test_module_plugin_sync_carries_real_description_and_author(
    tmp_path, captured_requests
):
    """No manifest.yml on disk (module plugin) -- description/author passed
    into sync_plugin_ai_tools must land in the marketplace create payload,
    not the old hardcoded empty-description/no-author placeholder."""
    await marketplace_sync.sync_plugin_ai_tools(
        "news",
        tmp_path,  # empty dir -- no manifest.yml/json
        module_ai_tools=[{"name": "get_news", "description": "Latest headlines"}],
        description="Fetches headlines from public RSS/Atom feeds.",
        author="Minder Team",
    )

    create_calls = [
        c for c in captured_requests if c[1].endswith("/v1/marketplace/plugins")
    ]
    assert len(create_calls) == 1
    body = create_calls[0][2]["json"]
    assert body["description"] == "Fetches headlines from public RSS/Atom feeds."
    assert body["author"] == "Minder Team"


@pytest.mark.asyncio
async def test_module_plugin_sync_without_author_falls_back_to_unknown(
    tmp_path, captured_requests
):
    """No author passed (caller has none) -- must not set an empty/falsy
    "author" key ourselves; get_or_create_marketplace_plugin's own
    `manifest.get("author", "Unknown")` default should apply instead."""
    await marketplace_sync.sync_plugin_ai_tools(
        "news",
        tmp_path,
        module_ai_tools=[{"name": "get_news", "description": "Latest headlines"}],
        description="Fetches headlines.",
        author=None,
    )

    create_calls = [
        c for c in captured_requests if c[1].endswith("/v1/marketplace/plugins")
    ]
    body = create_calls[0][2]["json"]
    assert body["author"] == "Unknown"


@pytest.mark.asyncio
async def test_module_plugin_sync_carries_databases_as_requires_services(
    tmp_path, captured_requests
):
    """The plugin's declared PluginMetadata.databases (backend services it
    needs at runtime, e.g. ["influxdb"]) must land in the marketplace create
    payload as requires_services -- surfaced on Available/Installed Plugins
    so a user can tell a plugin needs a bundle they haven't enabled (#484)."""
    await marketplace_sync.sync_plugin_ai_tools(
        "weather",
        tmp_path,
        module_ai_tools=[{"name": "get_weather", "description": "Current weather"}],
        description="Polls a keyless weather API.",
        author="Minder Team",
        databases=["influxdb"],
    )

    create_calls = [
        c for c in captured_requests if c[1].endswith("/v1/marketplace/plugins")
    ]
    assert len(create_calls) == 1
    body = create_calls[0][2]["json"]
    assert body["requires_services"] == ["influxdb"]


@pytest.mark.asyncio
async def test_no_ai_tools_still_gets_a_marketplace_row_but_skips_ai_sync(
    tmp_path, captured_requests
):
    """A plugin with no AI_TOOLS (e.g. telegraf) and no manifest must still
    get a marketplace catalog row -- found live: telegraf never appeared on
    Available/Installed Plugins at all, because the OLD code bailed out
    before ever calling get_or_create_marketplace_plugin for any plugin with
    nothing to import. Only the /ai/sync POST (nothing to import) is skipped."""
    await marketplace_sync.sync_plugin_ai_tools(
        "telegraf", tmp_path, module_ai_tools=None, description="x", author="y"
    )

    create_calls = [
        c for c in captured_requests if c[1].endswith("/v1/marketplace/plugins")
    ]
    assert len(create_calls) == 1

    ai_sync_calls = [c for c in captured_requests if c[1].endswith("/ai/sync")]
    assert ai_sync_calls == []


@pytest.mark.asyncio
async def test_plugin_dependencies_are_recorded_in_the_graph(
    tmp_path, captured_requests
):
    """ "network" declares plugin_dependencies=["telegraf"] (a real runtime
    dependency: network reads plugin_instances["telegraf"] directly) -- must
    resolve telegraf's marketplace id and POST a "requires" edge, in
    addition to network's own marketplace sync (#484)."""
    await marketplace_sync.sync_plugin_ai_tools(
        "network",
        tmp_path,
        module_ai_tools=[{"name": "scan", "description": "Scan the network"}],
        description="Autonomous nmap+SNMP discovery.",
        author="Minder Team",
        plugin_dependencies=["telegraf"],
    )

    dependency_calls = [
        c for c in captured_requests if c[1].endswith("/v1/graph/dependencies")
    ]
    assert len(dependency_calls) == 1
    params = dependency_calls[0][2]["params"]
    assert params["dependency_type"] == "requires"
    assert params["plugin_id"]
    assert params["depends_on"]

    # network's own row, plus telegraf's bare-resolve row.
    create_calls = [
        c for c in captured_requests if c[1].endswith("/v1/marketplace/plugins")
    ]
    assert len(create_calls) == 2


@pytest.mark.asyncio
async def test_dependency_resolution_never_overwrites_an_already_synced_target(
    tmp_path, monkeypatch
):
    """If telegraf already has a real marketplace row (its own sync ran
    first, or a prior boot), resolving it as a dependency target must be a
    pure lookup -- no PUT/reconcile call that could clobber its real
    description/requires_services with the bare placeholder this code path
    has no real metadata for."""
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":
            return _FakeResponse(
                200, {"plugins": [{"id": "real-telegraf-id", "name": "telegraf"}]}
            )
        if method == "PUT":
            raise AssertionError(
                "must not PUT/reconcile an already-synced dependency target"
            )
        if url.endswith("/v1/marketplace/plugins"):  # network's own create
            return _FakeResponse(201, {"id": "network-id"})
        return _FakeResponse(200, {"tools_imported": 1})

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )

    await marketplace_sync.sync_plugin_ai_tools(
        "network",
        tmp_path,
        module_ai_tools=[{"name": "scan", "description": "Scan the network"}],
        description="Autonomous nmap+SNMP discovery.",
        author="Minder Team",
        plugin_dependencies=["telegraf"],
    )

    dependency_calls = [c for c in calls if c[1].endswith("/v1/graph/dependencies")]
    assert len(dependency_calls) == 1
    assert dependency_calls[0][2]["params"]["depends_on"] == "real-telegraf-id"


@pytest.fixture
def existing_plugin_requests(monkeypatch):
    """Stub _mkt_request: search finds an existing plugin by name (the
    "already synced under the old buggy code" case), so the create branch
    should never fire and a PUT should reconcile metadata instead."""
    calls = []

    async def fake_request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        if method == "GET":  # the "search for existing plugin" call
            return _FakeResponse(
                200, {"plugins": [{"id": "existing-plugin-id", "name": "weather"}]}
            )
        if method == "PUT":
            return _FakeResponse(200, {"id": "existing-plugin-id"})
        return _FakeResponse(200, {"tools_imported": 1})  # /ai/sync

    monkeypatch.setattr(
        marketplace_sync, "_mkt_request", AsyncMock(side_effect=fake_request)
    )
    return calls


@pytest.mark.asyncio
async def test_existing_plugin_gets_metadata_reconciled_not_recreated(
    tmp_path, existing_plugin_requests
):
    """Found live: 4 first-party plugins were created under the old sync
    code and stayed stuck with empty description / author "Unknown" forever
    -- the "found existing" branch returned the id without ever writing the
    caller's current (correct) metadata back. A PUT must now reconcile the
    existing row instead of leaving it stale, and POST /plugins (create)
    must never fire for a plugin that already exists."""
    await marketplace_sync.sync_plugin_ai_tools(
        "weather",
        tmp_path,
        module_ai_tools=[{"name": "get_weather", "description": "Current weather"}],
        description="Current weather and forecasts.",
        author="Minder Team",
        databases=["influxdb"],
    )

    create_calls = [
        c
        for c in existing_plugin_requests
        if c[0] == "POST" and c[1].endswith("/v1/marketplace/plugins")
    ]
    assert create_calls == []

    put_calls = [c for c in existing_plugin_requests if c[0] == "PUT"]
    assert len(put_calls) == 1
    assert put_calls[0][1].endswith("/v1/marketplace/plugins/existing-plugin-id")
    body = put_calls[0][2]["json"]
    assert body["description"] == "Current weather and forecasts."
    assert body["author"] == "Minder Team"
    assert body["requires_services"] == ["influxdb"]
    # A single-sentence description must NOT become the display_name too --
    # found live: Available Plugins cards showed the exact same sentence
    # twice (once as the card title, once as the body) for every first-party
    # plugin, since every one of them has a one-sentence description. Falls
    # back to the plugin's own name instead of duplicating the description.
    assert body["display_name"] == "Weather"


@pytest.mark.asyncio
async def test_multi_sentence_description_gets_a_real_short_headline(
    tmp_path, existing_plugin_requests
):
    """A genuinely multi-sentence description is the one case the original
    "first sentence" derivation was meant for -- still honored."""
    await marketplace_sync.sync_plugin_ai_tools(
        "weather",
        tmp_path,
        module_ai_tools=[{"name": "get_weather", "description": "Current weather"}],
        description="Current weather and forecasts. Sourced from Open-Meteo, no API key needed.",
        author="Minder Team",
    )

    put_calls = [c for c in existing_plugin_requests if c[0] == "PUT"]
    body = put_calls[0][2]["json"]
    assert body["display_name"] == "Current weather and forecasts"
