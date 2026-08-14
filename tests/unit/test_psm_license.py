"""Unit tests for plugin-state-manager's license/tier gate (core/license.py).

Direct coverage was missing entirely — only the underlying vocabulary helper
(shared.models.tiers, see test_license_tiers.py) had tests. The gate FUNCTIONS
themselves (validate_tool_access/get_plugin_license_tier/check_plugin_license)
carry the actual fail-closed security behavior called out in their own
docstrings (#47, #142) -- an unknown/garbage required_tier must DENY, not fall
back to a permissive default; a paid tier without a validated license must
DENY unless the documented dev override env var is set. None of that was
guarded by a test before this file.

plugin-state-manager is a hyphenated service dir, so core.license is loaded by
path, same isolated-import pattern as test_psm_state_transitions.py.

core.license also does a bare `from config import settings` -- "config" is just
as collision-prone across this shared pytest process as "core"/"models" (every
service has its own config.py, all competing for the same bare module name),
and unlike those it can't just be evicted-and-reimported generically: whichever
service's directory happens to be first on sys.path at that moment wins, which
may not be plugin-state-manager's own config.py (with CATALOG_HTTP_TIMEOUT).
So this loads plugin-state-manager's own config.py fresh from its file and
registers *that* under "config" for the duration of the fixture, instead of a
bare `import config` left to ambient sys.path order.
"""

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

_PSM = Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"
_COLLISION_PRONE = ("core", "core.license", "models", "models.plugin_state", "config")


@pytest.fixture
def license_mod():
    saved_path = list(sys.path)
    saved_modules = {k: sys.modules[k] for k in _COLLISION_PRONE if k in sys.modules}
    for k in _COLLISION_PRONE:
        sys.modules.pop(k, None)
    sys.path.insert(0, str(_PSM))
    config_spec = importlib.util.spec_from_file_location("config", _PSM / "config.py")
    config_mod = importlib.util.module_from_spec(config_spec)
    sys.modules["config"] = config_mod
    config_spec.loader.exec_module(config_mod)
    try:
        yield importlib.import_module("core.license")
    finally:
        sys.path[:] = saved_path
        for k in _COLLISION_PRONE:
            sys.modules.pop(k, None)
        sys.modules.update(saved_modules)


class _FakeResponse:
    def __init__(self, json_data=None, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Minimal async-context-manager httpx.AsyncClient stand-in."""

    def __init__(self, json_data=None, status_code=200):
        self._json = json_data
        self._status_code = status_code

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        return _FakeResponse(self._json, self._status_code)


class _FakeConn:
    """Routes fetchrow by SQL text, same convention as test_psm_state_transitions.py."""

    def __init__(self, *, plugin_state_row=None, default_plugin_row=None):
        self.plugin_state_row = plugin_state_row
        self.default_plugin_row = default_plugin_row

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if "FROM plugin_states" in q:
            return self.plugin_state_row
        if "FROM default_plugins" in q:
            return self.default_plugin_row
        if "UPDATE plugin_states" in q:
            return {
                "plugin_name": args[2],
                "license_tier": args[0],
                "license_key": args[1],
            }
        return None


# --- validate_tool_access -----------------------------------------------


@pytest.mark.asyncio
async def test_validate_tool_access_tool_not_found_denies(monkeypatch, license_mod):
    monkeypatch.setattr(
        license_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(status_code=404),
    )
    result = await license_mod.validate_tool_access(None, "user-1", "ghost-tool")
    assert result["allowed"] is False
    assert result["user_tier"] == "unknown"
    assert "not found" in result["reason"]


@pytest.mark.asyncio
async def test_validate_tool_access_empty_tools_list_denies(monkeypatch, license_mod):
    monkeypatch.setattr(
        license_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(json_data={"tools": []}),
    )
    result = await license_mod.validate_tool_access(None, "user-1", "ghost-tool")
    assert result["allowed"] is False
    assert "not found" in result["reason"]


@pytest.mark.asyncio
async def test_validate_tool_access_community_tool_allowed(monkeypatch, license_mod):
    monkeypatch.setattr(
        license_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            json_data={"tools": [{"required_tier": "community"}]}
        ),
    )
    result = await license_mod.validate_tool_access(None, "user-1", "crypto_price")
    assert result["allowed"] is True
    assert result["reason"] is None


@pytest.mark.asyncio
async def test_validate_tool_access_pro_tool_denied_for_community_user(
    monkeypatch, license_mod
):
    monkeypatch.setattr(
        license_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(json_data={"tools": [{"required_tier": "pro"}]}),
    )
    result = await license_mod.validate_tool_access(None, "user-1", "premium_tool")
    assert result["allowed"] is False
    assert result["tier_required"] == "pro"
    assert "pro tier or higher" in result["reason"]


@pytest.mark.asyncio
async def test_validate_tool_access_legacy_professional_alias_matches_pro(
    monkeypatch, license_mod
):
    """#142: a marketplace-issued "professional" must rank identically to "pro"."""
    monkeypatch.setattr(
        license_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            json_data={"tools": [{"required_tier": "professional"}]}
        ),
    )
    result = await license_mod.validate_tool_access(None, "user-1", "premium_tool")
    assert result["allowed"] is False
    assert result["tier_required"] == "pro"


@pytest.mark.asyncio
async def test_validate_tool_access_unknown_required_tier_fails_closed(
    monkeypatch, license_mod
):
    """Regression guard: an unknown required_tier must DENY, not fall back to a
    permissive default. The old behavior used a dict .get(tier, 0) default, which
    fail-OPENED any tool with a garbage/unrecognized tier string to everyone."""
    monkeypatch.setattr(
        license_mod.httpx,
        "AsyncClient",
        lambda **kw: _FakeAsyncClient(
            json_data={"tools": [{"required_tier": "platinum"}]}
        ),
    )
    result = await license_mod.validate_tool_access(None, "user-1", "weird_tool")
    assert result["allowed"] is False


# --- get_plugin_license_tier ---------------------------------------------


@pytest.mark.asyncio
async def test_get_plugin_license_tier_from_plugin_states_row(license_mod):
    conn = _FakeConn(plugin_state_row={"license_tier": "enterprise"})
    tier = await license_mod.get_plugin_license_tier(conn, "some-plugin")
    assert tier is license_mod.LicenseTier.ENTERPRISE


@pytest.mark.asyncio
async def test_get_plugin_license_tier_falls_back_to_default_plugins_row(license_mod):
    conn = _FakeConn(plugin_state_row=None, default_plugin_row={"min_tier": "pro"})
    tier = await license_mod.get_plugin_license_tier(conn, "some-plugin")
    assert tier is license_mod.LicenseTier.PRO


@pytest.mark.asyncio
async def test_get_plugin_license_tier_defaults_to_community(license_mod):
    conn = _FakeConn(plugin_state_row=None, default_plugin_row=None)
    tier = await license_mod.get_plugin_license_tier(conn, "unregistered-plugin")
    assert tier is license_mod.LicenseTier.COMMUNITY


@pytest.mark.asyncio
async def test_get_plugin_license_tier_normalizes_legacy_professional(license_mod):
    conn = _FakeConn(plugin_state_row={"license_tier": "professional"})
    tier = await license_mod.get_plugin_license_tier(conn, "some-plugin")
    assert tier is license_mod.LicenseTier.PRO


# --- check_plugin_license -------------------------------------------------


@pytest.mark.asyncio
async def test_check_plugin_license_community_needs_no_key(license_mod):
    conn = _FakeConn(plugin_state_row={"license_tier": "community"})
    result = await license_mod.check_plugin_license(conn, "free-plugin")
    assert result["valid"] is True


@pytest.mark.asyncio
async def test_check_plugin_license_paid_tier_without_key_invalid(license_mod):
    conn = _FakeConn(plugin_state_row={"license_tier": "pro"})
    result = await license_mod.check_plugin_license(conn, "paid-plugin")
    assert result["valid"] is False
    assert "License key required" in result["message"]


@pytest.mark.asyncio
async def test_check_plugin_license_paid_tier_with_key_fails_closed_by_default(
    monkeypatch, license_mod
):
    """#47: no real license/subscription store exists yet, so a key must be
    REJECTED by default -- the old behavior accepted any non-empty string."""
    monkeypatch.delenv("MINDER_ALLOW_UNVALIDATED_LICENSES", raising=False)
    conn = _FakeConn(plugin_state_row={"license_tier": "pro"})
    result = await license_mod.check_plugin_license(
        conn, "paid-plugin", license_key="anything-at-all"
    )
    assert result["valid"] is False
    assert "not yet" in result["message"]


@pytest.mark.asyncio
async def test_check_plugin_license_dev_override_accepts_unvalidated_key(
    monkeypatch, license_mod
):
    monkeypatch.setenv("MINDER_ALLOW_UNVALIDATED_LICENSES", "1")
    conn = _FakeConn(plugin_state_row={"license_tier": "enterprise"})
    result = await license_mod.check_plugin_license(
        conn, "paid-plugin", license_key="anything-at-all"
    )
    assert result["valid"] is True
    assert "dev override" in result["message"]


# --- update_plugin_license ------------------------------------------------


@pytest.mark.asyncio
async def test_update_plugin_license_returns_updated_row(license_mod):
    conn = _FakeConn()
    result = await license_mod.update_plugin_license(
        conn, "some-plugin", license_mod.LicenseTier.PRO, license_key="key-123"
    )
    assert result == {
        "plugin_name": "some-plugin",
        "license_tier": "pro",
        "license_key": "key-123",
    }


@pytest.mark.asyncio
async def test_update_plugin_license_unknown_plugin_returns_none(license_mod):
    class _NoRowConn:
        async def fetchrow(self, query, *args):
            return None

    result = await license_mod.update_plugin_license(
        _NoRowConn(), "ghost-plugin", license_mod.LicenseTier.COMMUNITY
    )
    assert result is None
