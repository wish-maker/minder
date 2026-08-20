"""Unit tests for plugin-state-manager state transitions (#203).

Guards the fix that stopped the state layer from (a) phantom-creating an unknown
plugin on API-driven ``enable`` and (b) collapsing "not found" / business-rule
conflicts into a blanket HTTP 400.

- ``enable_plugin`` auto-creates a row ONLY when ``allow_create=True`` (the bootstrap
  path); an API-driven enable of an unknown plugin must raise ``PluginNotFoundError``
  (→ 404) instead of silently materialising an ENABLED phantom.
- ``disable_plugin`` on an unknown plugin raises ``PluginNotFoundError`` (→ 404), not
  the old ``StateTransitionError`` that the route mapped to 400.
- disabling a required plugin without force raises ``RequiredPluginError`` (→ 409).

plugin-state-manager is a hyphenated service dir, so ``core.state`` is loaded by path.
Its ``from models.plugin_state import ...`` needs the service dir on ``sys.path``; the
fixture snapshots and restores ``sys.path`` / ``sys.modules`` so other services' equally
named ``core`` / ``models`` packages aren't poisoned for the rest of the run.
"""

import importlib
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest

_PSM = Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"


_STATE_MOD_KEYS = ("core", "core.state", "models", "models.plugin_state", "config")


@pytest.fixture
def state_mod():
    """Import plugin-state-manager's core.state in isolation, then restore globals.

    "config" joined this reset set once core/state.py started doing
    `from config import settings` (#751, plugin_exists_in_registry) -- without
    it, a bare "config" module cached in sys.modules from whichever OTHER
    service's test ran first in this pytest process (every service has its own
    top-level config.py, all sharing that same bare module name) gets reused
    here instead of plugin-state-manager's own, and CATALOG_HTTP_TIMEOUT/
    PLUGIN_REGISTRY_URL resolve against the wrong Settings subclass.
    """
    saved_path = list(sys.path)
    saved_modules = {k: sys.modules[k] for k in _STATE_MOD_KEYS if k in sys.modules}
    for k in _STATE_MOD_KEYS:
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_PSM))
    try:
        yield importlib.import_module("core.state")
    finally:
        sys.path[:] = saved_path
        for k in _STATE_MOD_KEYS:
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


class FakeConn:
    """Minimal asyncpg-connection stand-in routing on the SQL text.

    ``default_required``: None => not a default plugin; bool => a default_plugins row
    with that ``required`` flag. ``existing_state``: the plugin_states row (dict) or None.
    """

    def __init__(
        self,
        *,
        default_required=None,
        existing_state=None,
        dependents=None,
        dependent_plugins_rows=None,
        list_rows=None,
        dep_graph_rows=None,
    ):
        self.default_required = default_required
        self.existing_state = existing_state
        self.inserts = []
        self.dependents = dependents or []
        self.dependent_plugins_rows = dependent_plugins_rows or []
        self.list_rows = list_rows if list_rows is not None else []
        self.dep_graph_rows = dep_graph_rows or []

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "FROM default_plugins" in q:
            if self.default_required is None:
                return None
            return {"required": self.default_required}
        if q.startswith("SELECT * FROM plugin_states"):
            return self.existing_state
        if "INSERT INTO plugin_states" in q:
            # #908: create_plugin_state now also passes enabled_at/disabled_at so
            # a row materialized directly in ENABLED state (the #751 auto-create
            # path) carries a non-null enabled_at like every other enabled row.
            name, state, tier, enabled_at, disabled_at = args
            # Real asyncpg returns a uuid.UUID object for a UUID column and a raw
            # JSON *string* for a JSONB column (no codec is registered anywhere --
            # shared/db/pool.py calls plain asyncpg.create_pool()) -- NOT already
            # a str/dict like a naive fake would return. Matching that here is
            # what actually exercises _record_to_dict's normalization; a fake that
            # returns pre-normalized types would pass even with the old `dict(row)`
            # bug (#confirmed: that's why the pre-fix version of this test file
            # never caught it).
            row = {
                "id": uuid.uuid4(),
                "plugin_name": name,
                "state": state,
                "license_tier": tier,
                "config": "{}",
                "enabled_at": enabled_at,
                "disabled_at": disabled_at,
            }
            self.inserts.append(row)
            return row
        if "UPDATE plugin_states" in q and "RETURNING *" in q:
            state = args[0]
            row = {
                "id": uuid.uuid4(),
                "plugin_name": self.existing_state["plugin_name"],
                "state": state,
                "license_tier": self.existing_state.get("license_tier", "community"),
                "config": json.dumps(self.existing_state.get("config", {})),
            }
            self.existing_state = row
            return row
        return None

    async def fetch(self, query, *args):
        q = " ".join(query.split())
        if "FROM plugin_dependencies pd" in q and "JOIN default_plugins dp" in q:
            return self.dependent_plugins_rows
        if "FROM plugin_dependencies" in q:
            return self.dependents
        if "FROM default_plugins dp" in q and "LEFT JOIN plugin_dependencies pd" in q:
            return self.dep_graph_rows
        if "FROM plugin_states" in q:
            return self.list_rows
        return []


async def test_enable_unknown_plugin_raises_not_found(state_mod):
    conn = FakeConn(default_required=None, existing_state=None)
    with pytest.raises(state_mod.PluginNotFoundError):
        await state_mod.enable_plugin(conn, "does-not-exist")
    assert conn.inserts == []  # regression: no phantom row materialised


async def test_enable_bootstrap_path_still_creates(state_mod):
    conn = FakeConn(default_required=None, existing_state=None)
    row = await state_mod.enable_plugin(
        conn, "crypto", reason="system_bootstrap", allow_create=True
    )
    assert row["state"] == state_mod.PluginState.ENABLED.value
    assert conn.inserts and conn.inserts[0]["plugin_name"] == "crypto"


async def test_auto_create_on_enable_stamps_enabled_at(state_mod):
    """#908: a plugin_states row materialized directly in ENABLED state (the
    #751 first-enable auto-create path) must carry a non-null ``enabled_at``,
    matching an installed→enabled transition -- not be silently left NULL and
    inconsistent with every other enabled row."""
    conn = FakeConn(default_required=None, existing_state=None)
    row = await state_mod.enable_plugin(
        conn, "crypto", reason="system_bootstrap", allow_create=True
    )
    assert row["state"] == state_mod.PluginState.ENABLED.value
    assert row["enabled_at"] is not None
    assert row["disabled_at"] is None


async def test_disable_unknown_plugin_raises_not_found(state_mod):
    conn = FakeConn(default_required=None, existing_state=None)
    with pytest.raises(state_mod.PluginNotFoundError):
        await state_mod.disable_plugin(conn, "does-not-exist")


async def test_disable_required_plugin_without_force_conflicts(state_mod):
    conn = FakeConn(default_required=True, existing_state={"state": "enabled"})
    with pytest.raises(state_mod.RequiredPluginError):
        await state_mod.disable_plugin(conn, "core-thing", force=False)


async def test_create_plugin_state_normalizes_uuid_and_jsonb(state_mod):
    """#confirmed: create_plugin_state used to `return dict(row)` instead of
    `_record_to_dict(row)` -- against a real asyncpg row (uuid.UUID id, JSONB
    returned as a raw string), that shipped an unstringified UUID and an
    unparsed JSON string straight into PluginStateResponse(**state), which
    requires `id: str` / `config: Dict` and would 500 on every real enable of
    a not-yet-tracked plugin."""
    conn = FakeConn(default_required=None, existing_state=None)
    row = await state_mod.enable_plugin(
        conn, "crypto", reason="system_bootstrap", allow_create=True
    )
    assert isinstance(row["id"], str)
    assert row["config"] == {}


async def test_update_plugin_state_normalizes_uuid_and_jsonb(state_mod):
    """Same bug, the update-path sibling: update_plugin_state used to
    `return dict(row)` too, so every real enable/disable of an
    already-tracked plugin (the common case, not just first-time bootstrap)
    also 500'd against a real database."""
    conn = FakeConn(
        default_required=None,
        existing_state={
            "plugin_name": "crypto",
            "state": "installed",
            "license_tier": "community",
            "config": {"threshold": 5},
        },
    )
    row = await state_mod.enable_plugin(conn, "crypto")
    assert isinstance(row["id"], str)
    assert row["config"] == {"threshold": 5}
    assert row["state"] == state_mod.PluginState.ENABLED.value


# --- enable_plugin: remaining branches ---------------------------------------


async def test_enable_required_plugin_non_bootstrap_still_enables(state_mod):
    """A required plugin enabled with a non-bootstrap reason only logs a
    warning -- it does NOT block the enable (only disable enforces force=True
    for required plugins)."""
    conn = FakeConn(
        default_required=True,
        existing_state={"plugin_name": "core-thing", "state": "installed"},
    )
    row = await state_mod.enable_plugin(conn, "core-thing", reason="user click")
    assert row["state"] == state_mod.PluginState.ENABLED.value


async def test_enable_already_enabled_plugin_is_a_noop(state_mod):
    existing = {"state": "enabled", "plugin_name": "crypto"}
    conn = FakeConn(default_required=None, existing_state=existing)
    row = await state_mod.enable_plugin(conn, "crypto")
    assert (
        row == existing
    )  # returned unchanged (fresh dict via _record_to_dict, same content), no UPDATE issued


async def test_enable_from_invalid_state_raises_transition_error(state_mod):
    conn = FakeConn(default_required=None, existing_state={"state": "pending"})
    with pytest.raises(state_mod.StateTransitionError):
        await state_mod.enable_plugin(conn, "weird-plugin")


# --- disable_plugin: remaining branches --------------------------------------


async def test_disable_with_non_required_dependents_still_disables(state_mod):
    conn = FakeConn(
        default_required=None,
        existing_state={"state": "enabled", "plugin_name": "core-lib"},
        dependents=[{"plugin_name": "weather", "required": False}],
    )
    row = await state_mod.disable_plugin(conn, "core-lib")
    assert row["state"] == state_mod.PluginState.DISABLED.value


async def test_disable_with_required_dependent_raises_transition_error(state_mod):
    conn = FakeConn(
        default_required=None,
        existing_state={"state": "enabled", "plugin_name": "core-lib"},
        dependents=[{"plugin_name": "weather", "required": True}],
    )
    with pytest.raises(state_mod.StateTransitionError):
        await state_mod.disable_plugin(conn, "core-lib")


async def test_disable_already_disabled_plugin_is_a_noop(state_mod):
    existing = {"state": "disabled", "plugin_name": "crypto"}
    conn = FakeConn(default_required=None, existing_state=existing)
    row = await state_mod.disable_plugin(conn, "crypto")
    assert (
        row == existing
    )  # returned unchanged (fresh dict via _record_to_dict, same content), no UPDATE issued


async def test_disable_from_invalid_state_raises_transition_error(state_mod):
    conn = FakeConn(default_required=None, existing_state={"state": "pending"})
    with pytest.raises(state_mod.StateTransitionError):
        await state_mod.disable_plugin(conn, "weird-plugin")


# --- list_plugin_states -------------------------------------------------


async def test_list_plugin_states_returns_all_when_unfiltered(state_mod):
    rows = [
        {"plugin_name": "a", "state": "enabled", "config": "{}"},
        {"plugin_name": "b", "state": "disabled", "config": "{}"},
    ]
    conn = FakeConn(list_rows=rows)

    result = await state_mod.list_plugin_states(conn, None)

    assert [r["plugin_name"] for r in result] == ["a", "b"]
    assert result[0]["config"] == {}  # _record_to_dict's JSONB parsing applied


async def test_list_plugin_states_applies_state_filter(state_mod):
    captured = {}

    class _FilterConn(FakeConn):
        async def fetch(self, query, *args):
            captured["args"] = args
            return await super().fetch(query, *args)

    conn = _FilterConn(
        list_rows=[{"plugin_name": "a", "state": "enabled", "config": "{}"}]
    )

    result = await state_mod.list_plugin_states(conn, state_mod.PluginState.ENABLED)

    assert captured["args"] == ("enabled",)
    assert len(result) == 1


# --- get_dependent_plugins ----------------------------------------------


async def test_get_dependent_plugins_returns_normalized_rows(state_mod):
    rows = [
        {
            "plugin_name": "weather",
            "required": False,
            "auto_enable": True,
            "is_required": False,
        }
    ]
    conn = FakeConn(dependent_plugins_rows=rows)

    result = await state_mod.get_dependent_plugins(conn, "core-lib")

    assert result == rows


# --- resolve_dependencies ------------------------------------------------


async def test_resolve_dependencies_returns_topological_order(state_mod):
    # c depends on b, b depends on a -- enable order must be a, b, c.
    rows = [
        {"plugin_name": "a", "depends_on": None, "required": False},
        {"plugin_name": "b", "depends_on": "a", "required": True},
        {"plugin_name": "c", "depends_on": "b", "required": True},
    ]
    conn = FakeConn(dep_graph_rows=rows)

    order = await state_mod.resolve_dependencies(conn, "c")

    assert order.index("a") < order.index("b") < order.index("c")


async def test_update_plugin_state_generic_branch_for_non_enabled_disabled_state(
    state_mod,
):
    """update_plugin_state's third query branch (neither ENABLED nor DISABLED)
    -- no enable_plugin/disable_plugin call site reaches it, but it's a public
    function other callers could use directly for e.g. an ERROR transition."""
    conn = FakeConn(
        existing_state={"plugin_name": "crypto", "state": "installed", "config": {}}
    )

    row = await state_mod.update_plugin_state(
        conn, "crypto", state_mod.PluginState.ERROR
    )

    assert row["state"] == state_mod.PluginState.ERROR.value


async def test_resolve_dependencies_raises_on_circular_dependency(state_mod):
    rows = [
        {"plugin_name": "a", "depends_on": "b", "required": True},
        {"plugin_name": "b", "depends_on": "a", "required": True},
    ]
    conn = FakeConn(dep_graph_rows=rows)

    with pytest.raises(ValueError, match="Circular dependency"):
        await state_mod.resolve_dependencies(conn, "a")


class _FakeRegistryResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class _FakeRegistryClient:
    def __init__(self, status_code):
        self._status_code = status_code
        self.requested_url = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url):
        self.requested_url = url
        return _FakeRegistryResponse(self._status_code)


async def test_plugin_exists_in_registry_true_for_200(state_mod):
    fake_client = _FakeRegistryClient(200)
    with patch.object(state_mod.httpx, "AsyncClient", return_value=fake_client):
        assert await state_mod.plugin_exists_in_registry("weather-plus") is True
    assert fake_client.requested_url.endswith("/v1/plugins/weather-plus")


async def test_plugin_exists_in_registry_false_for_404(state_mod):
    fake_client = _FakeRegistryClient(404)
    with patch.object(state_mod.httpx, "AsyncClient", return_value=fake_client):
        assert await state_mod.plugin_exists_in_registry("ghost") is False


async def test_plugin_exists_in_registry_propagates_connection_errors(state_mod):
    """A plugin-registry outage must raise, not resolve to False -- the caller
    (routes/state.py) is what turns this into a 503, never a silent 404."""

    class _BrokenClient(_FakeRegistryClient):
        async def get(self, url):
            raise ConnectionError("connection refused")

    with patch.object(state_mod.httpx, "AsyncClient", return_value=_BrokenClient(200)):
        with pytest.raises(ConnectionError):
            await state_mod.plugin_exists_in_registry("weather-plus")
