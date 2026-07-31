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
import sys
from pathlib import Path

import pytest

_PSM = Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"


@pytest.fixture
def state_mod():
    """Import plugin-state-manager's core.state in isolation, then restore globals."""
    saved_path = list(sys.path)
    saved_modules = {
        k: sys.modules[k]
        for k in ("core", "core.state", "models", "models.plugin_state")
        if k in sys.modules
    }
    for k in ("core", "core.state", "models", "models.plugin_state"):
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_PSM))
    try:
        yield importlib.import_module("core.state")
    finally:
        sys.path[:] = saved_path
        for k in ("core", "core.state", "models", "models.plugin_state"):
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


class FakeConn:
    """Minimal asyncpg-connection stand-in routing on the SQL text.

    ``default_required``: None => not a default plugin; bool => a default_plugins row
    with that ``required`` flag. ``existing_state``: the plugin_states row (dict) or None.
    """

    def __init__(self, *, default_required=None, existing_state=None):
        self.default_required = default_required
        self.existing_state = existing_state
        self.inserts = []

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "FROM default_plugins" in q:
            if self.default_required is None:
                return None
            return {"required": self.default_required}
        if q.startswith("SELECT * FROM plugin_states"):
            return self.existing_state
        if "INSERT INTO plugin_states" in q:
            name, state, tier = args
            row = {
                "id": "00000000-0000-0000-0000-000000000000",
                "plugin_name": name,
                "state": state,
                "license_tier": tier,
                "config": {},
                "metadata": {},
            }
            self.inserts.append(row)
            return row
        return None

    async def fetch(self, query, *args):
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


async def test_disable_unknown_plugin_raises_not_found(state_mod):
    conn = FakeConn(default_required=None, existing_state=None)
    with pytest.raises(state_mod.PluginNotFoundError):
        await state_mod.disable_plugin(conn, "does-not-exist")


async def test_disable_required_plugin_without_force_conflicts(state_mod):
    conn = FakeConn(default_required=True, existing_state={"state": "enabled"})
    with pytest.raises(state_mod.RequiredPluginError):
        await state_mod.disable_plugin(conn, "core-thing", force=False)
