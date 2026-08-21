"""Unit tests filling routes/management.py's remaining coverage gaps (60%).

test_marketplace_install_plugin.py already locks in install_plugin's UUID-
serialization fix and the MAX_PLUGINS_PER_USER cap. test_marketplace_plugin_
installations_admin.py covers the admin listing endpoint. This adds
everything else: install_plugin's plugin-not-found 404, and the entire
uninstall/enable/disable trio (not-installed 404 + success path for each --
none of the three had ANY coverage before this).

Same isolated-import + fake-pool pattern as the sibling suite. Routes are
called directly as plain async functions (bypassing FastAPI's Depends/routing
layer), matching test_marketplace_install_plugin.py's precedent.
"""

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


(management,) = _isolated_import("routes.management")


class _FakeConn:
    def __init__(self, plugin_row=None, existing_row=None, dep_rows=None):
        self._plugin_row = plugin_row
        # Mutable, evolving record -- #892's install_plugin fix issues
        # multiple statements against the SAME row within one call (write
        # enabled=FALSE, run the dependency check, flip to enabled=TRUE), so
        # a frozen snapshot re-returned by every fetchrow wouldn't reflect
        # that; this needs to actually mutate across the call.
        self._installation = dict(existing_row) if existing_row else None
        # Rows returned for the #748 dependency/dependent lookup `fetch()`
        # calls -- keyed by plugin_id so both enable's (dependency) and
        # disable's (dependent) queries can share one fake conn.
        self._dep_rows = {r["plugin_id"]: r for r in (dep_rows or [])}
        self.executed = []

    async def fetchrow(self, query, *args):
        if "FROM marketplace_plugins" in query:
            return self._plugin_row
        if "INSERT INTO marketplace_installations" in query:
            user_id, plugin_id = args
            self._installation = {
                "id": uuid.uuid4(),
                "user_id": user_id,
                "plugin_id": plugin_id,
                "version": None,
                "status": "installed",
                "enabled": False,
                "config_json": None,
                "installed_at": datetime.now(timezone.utc),
                "last_updated_at": datetime.now(timezone.utc),
            }
            return dict(self._installation)
        if "UPDATE marketplace_installations" in query and "RETURNING" in query:
            if self._installation is None:
                return None
            if "enabled = TRUE" in query:
                self._installation["enabled"] = True
            elif "enabled = FALSE" in query:
                self._installation["enabled"] = False
            if "status = 'installed'" in query:
                self._installation["status"] = "installed"
            return dict(self._installation)
        if "FROM marketplace_installations" in query and "SELECT *" in query:
            return dict(self._installation) if self._installation else None
        return None

    async def fetch(self, query, *args):
        # Both #748 lookups select plugin_id (+ enabled) FROM
        # marketplace_installations WHERE plugin_id = ANY(...) -- args[-1] is
        # always the id list here (user_id is args[0]). Mirror the real SQL's
        # "AND enabled = TRUE" filter (disable's dependent-blocking query) --
        # skipping this made the fake `fetch()` return disabled dependents as
        # if they were still enabled, which is not what the real query does.
        ids = args[-1]
        rows = [self._dep_rows[i] for i in ids if i in self._dep_rows]
        if "enabled = TRUE" in query:
            rows = [r for r in rows if r["enabled"]]
        return rows

    async def fetchval(self, query, *args):
        # install_plugin's MAX_PLUGINS_PER_USER cap check (fresh-install
        # branch only) -- 0 so it never blocks these #892 tests, which are
        # about the dependency check, not the cap (see
        # test_marketplace_install_plugin.py for cap-specific coverage).
        if "COUNT(*) FROM marketplace_installations" in query:
            return 0
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeNeo4j:
    """Fake Neo4jClient for #748's dependency-graph checks. Defaults to "no
    dependencies/dependents" so every pre-#748 test continues to exercise the
    exact same enable/disable behavior unmodified.

    ``raises``: simulate Neo4j being unreachable (found live in CI -- the e2e
    harness deliberately doesn't wire marketplace to a real Neo4j, per
    conftest.py's docstring, and the driver call was unguarded until CI caught
    it with an unclean 500)."""

    def __init__(self, dependencies=None, dependents=None, raises=None):
        self._dependencies = dependencies or []
        self._dependents = dependents or []
        self._raises = raises

    async def get_dependency_chain(self, plugin_id):
        if self._raises:
            raise self._raises
        return self._dependencies

    async def get_dependent_plugins(self, plugin_id):
        if self._raises:
            raise self._raises
        return self._dependents


def _dep_installation_row(plugin_id, enabled):
    return {"plugin_id": plugin_id, "enabled": enabled}


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _FakeAcquire(self._conn)


def _installation_row(plugin_id, **overrides):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid.uuid4(),
        "user_id": "4",
        "plugin_id": plugin_id,
        "version": None,
        "status": "installed",
        "enabled": True,
        "config_json": None,
        "installed_at": now,
        "last_updated_at": now,
    }
    base.update(overrides)
    return base


# --- install_plugin: plugin-not-found 404 ------------------------------------


@pytest.mark.asyncio
async def test_install_plugin_404_when_plugin_does_not_exist(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(plugin_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.install_plugin(
            current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
        )

    assert exc.value.status_code == 404


# --- install_plugin: #892 dependency enforcement -----------------------------


@pytest.mark.asyncio
async def test_install_plugin_fresh_install_lands_enabled_when_no_dependency(
    monkeypatch,
):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(plugin_row={"id": plugin_id, "status": "approved"}, existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.install_plugin(
        current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=_FakeNeo4j()
    )

    assert result.enabled is True
    assert result.status == "installed"


@pytest.mark.asyncio
async def test_install_plugin_rejects_when_dependency_never_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    dep_id = str(uuid.uuid4())
    conn = _FakeConn(plugin_row={"id": plugin_id, "status": "approved"}, existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependencies=[{"plugin_id": dep_id, "name": "telegraf"}])

    with pytest.raises(HTTPException) as exc:
        await management.install_plugin(
            current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=neo4j
        )

    assert exc.value.status_code == 409
    assert "telegraf" in exc.value.detail
    # The row must never have been left enabled by the failed install.
    assert conn._installation["enabled"] is False


@pytest.mark.asyncio
async def test_install_plugin_succeeds_and_auto_enables_installed_dependency(
    monkeypatch,
):
    plugin_id = str(uuid.uuid4())
    dep_id = str(uuid.uuid4())
    conn = _FakeConn(
        plugin_row={"id": plugin_id, "status": "approved"},
        existing_row=None,
        dep_rows=[_dep_installation_row(dep_id, enabled=False)],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependencies=[{"plugin_id": dep_id, "name": "telegraf"}])

    result = await management.install_plugin(
        current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=neo4j
    )

    assert result.enabled is True
    # The dependency itself gets auto-enabled too (mirrors /enable's own
    # behavior, since install now runs the same check).
    assert any(
        "SET enabled = TRUE" in q and args == ("4", dep_id) for q, args in conn.executed
    )


@pytest.mark.asyncio
async def test_install_plugin_reinstall_rejects_when_dependency_disabled_since(
    monkeypatch,
):
    """Re-installing (e.g. after a prior uninstall) an already-known plugin
    must run the SAME dependency check as a fresh install -- #892 found this
    branch was the OTHER unconditional-enable path."""
    plugin_id = str(uuid.uuid4())
    dep_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, status="uninstalled", enabled=False)
    conn = _FakeConn(
        plugin_row={"id": plugin_id, "status": "approved"},
        existing_row=existing,
        dep_rows=[_dep_installation_row(dep_id, enabled=False)],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependencies=[{"plugin_id": dep_id, "name": "telegraf"}])
    # No installation row for the dependency at all -- must reject.
    conn._dep_rows = {}

    with pytest.raises(HTTPException) as exc:
        await management.install_plugin(
            current_user={"sub": "4"}, plugin_id=plugin_id, neo4j=neo4j
        )

    assert exc.value.status_code == 409
    assert conn._installation["enabled"] is False


# --- uninstall_plugin ----------------------------------------------------------


@pytest.mark.asyncio
async def test_uninstall_plugin_404_when_not_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.uninstall_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_uninstall_plugin_success_updates_status(monkeypatch):
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.uninstall_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}
    )

    assert result == {"status": "uninstalled", "plugin_id": plugin_id}
    query, args = conn.executed[0]
    assert "SET status = 'uninstalled'" in query
    assert args == (existing["id"],)


# --- enable_plugin ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_enable_plugin_404_when_not_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.enable_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=_FakeNeo4j()
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_enable_plugin_success_updates_enabled(monkeypatch):
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.enable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=_FakeNeo4j()
    )

    assert result == {
        "status": "enabled",
        "plugin_id": plugin_id,
        "auto_enabled_dependencies": [],
    }
    query, args = conn.executed[0]
    assert "SET enabled = TRUE" in query
    assert args == (existing["id"],)


@pytest.mark.asyncio
async def test_enable_plugin_degrades_gracefully_when_neo4j_unreachable(
    monkeypatch,
):
    """A Neo4j connectivity failure must not block enable entirely -- the
    dependency graph is a safety net on top of enable's real job, not a
    precondition for it (found live: this used to be a raw 500, then an
    unhelpful 503 that made a Neo4j hiccup block plugin management)."""
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(raises=ConnectionError("Neo4j unreachable"))

    result = await management.enable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert result == {
        "status": "enabled",
        "plugin_id": plugin_id,
        "auto_enabled_dependencies": [],
    }


@pytest.mark.asyncio
async def test_enable_plugin_still_500s_on_a_non_connectivity_neo4j_error(
    monkeypatch,
):
    """Only reachability degrades gracefully -- a real bug in the query
    still surfaces as a 500, not silently swallowed."""
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(raises=ValueError("malformed Cypher result"))

    with pytest.raises(HTTPException) as exc:
        await management.enable_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
        )

    assert exc.value.status_code == 500


# --- enable_plugin: #748 dependency auto-enable ---------------------------------


@pytest.mark.asyncio
async def test_enable_plugin_auto_enables_a_disabled_dependency(monkeypatch):
    plugin_id = str(uuid.uuid4())
    dep_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(
        existing_row=existing,
        dep_rows=[_dep_installation_row(dep_id, enabled=False)],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependencies=[{"plugin_id": dep_id, "name": "telegraf"}])

    result = await management.enable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert result["auto_enabled_dependencies"] == ["telegraf"]
    dep_update = next(
        (q, a) for q, a in conn.executed if "user_id = $1 AND plugin_id = $2" in q
    )
    assert dep_update[1] == ("4", dep_id)


@pytest.mark.asyncio
async def test_enable_plugin_does_not_touch_an_already_enabled_dependency(
    monkeypatch,
):
    plugin_id = str(uuid.uuid4())
    dep_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(
        existing_row=existing,
        dep_rows=[_dep_installation_row(dep_id, enabled=True)],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependencies=[{"plugin_id": dep_id, "name": "telegraf"}])

    result = await management.enable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert result["auto_enabled_dependencies"] == []
    # Only the plugin's own enable UPDATE ran -- no dependency UPDATE.
    assert len(conn.executed) == 1


@pytest.mark.asyncio
async def test_enable_plugin_rejects_when_dependency_never_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    dep_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(existing_row=existing, dep_rows=[])  # dependency has no row
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependencies=[{"plugin_id": dep_id, "name": "telegraf"}])

    with pytest.raises(HTTPException) as exc:
        await management.enable_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
        )

    assert exc.value.status_code == 409
    assert "telegraf" in exc.value.detail
    # Nothing was mutated -- the plugin itself was never enabled either.
    assert conn.executed == []


@pytest.mark.asyncio
async def test_enable_plugin_auto_enables_a_transitive_dependency_chain(monkeypatch):
    plugin_id = str(uuid.uuid4())
    dep_b, dep_c = str(uuid.uuid4()), str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=False)
    conn = _FakeConn(
        existing_row=existing,
        dep_rows=[
            _dep_installation_row(dep_b, enabled=False),
            _dep_installation_row(dep_c, enabled=False),
        ],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    # get_dependency_chain already returns the full transitive set in one call.
    neo4j = _FakeNeo4j(
        dependencies=[
            {"plugin_id": dep_b, "name": "b"},
            {"plugin_id": dep_c, "name": "c"},
        ]
    )

    result = await management.enable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert set(result["auto_enabled_dependencies"]) == {"b", "c"}


# --- disable_plugin --------------------------------------------------------------


@pytest.mark.asyncio
async def test_disable_plugin_404_when_not_installed(monkeypatch):
    plugin_id = str(uuid.uuid4())
    conn = _FakeConn(existing_row=None)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    with pytest.raises(HTTPException) as exc:
        await management.disable_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=_FakeNeo4j()
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_disable_plugin_success_updates_enabled(monkeypatch):
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))

    result = await management.disable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=_FakeNeo4j()
    )

    assert result == {"status": "disabled", "plugin_id": plugin_id}
    query, args = conn.executed[0]
    assert "SET enabled = FALSE" in query
    assert args == (existing["id"],)


@pytest.mark.asyncio
async def test_disable_plugin_degrades_gracefully_when_neo4j_unreachable(
    monkeypatch,
):
    """A Neo4j connectivity failure must not block disable entirely -- same
    rationale as the enable-side test above (found live: this used to be a
    raw 500, then an unhelpful 503 that made a Neo4j hiccup block plugin
    management -- exactly what e2e's test_disable_then_enable_round_trip
    caught, since that harness deliberately doesn't wire marketplace to a
    real Neo4j, per conftest.py's docstring)."""
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(raises=ConnectionError("Neo4j unreachable"))

    result = await management.disable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert result == {"status": "disabled", "plugin_id": plugin_id}


@pytest.mark.asyncio
async def test_disable_plugin_still_500s_on_a_non_connectivity_neo4j_error(
    monkeypatch,
):
    """Only reachability degrades gracefully -- a real bug in the query
    still surfaces as a 500, not silently swallowed."""
    plugin_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    conn = _FakeConn(existing_row=existing)
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(raises=ValueError("malformed Cypher result"))

    with pytest.raises(HTTPException) as exc:
        await management.disable_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
        )

    assert exc.value.status_code == 500


# --- disable_plugin: #748 dependent-blocking -----------------------------------


@pytest.mark.asyncio
async def test_disable_plugin_blocked_by_an_enabled_dependent(monkeypatch):
    plugin_id = str(uuid.uuid4())
    dependent_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    conn = _FakeConn(
        existing_row=existing,
        dep_rows=[_dep_installation_row(dependent_id, enabled=True)],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependents=[{"plugin_id": dependent_id, "name": "network"}])

    with pytest.raises(HTTPException) as exc:
        await management.disable_plugin(
            plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
        )

    assert exc.value.status_code == 409
    assert "network" in exc.value.detail
    # Nothing was mutated -- disable never ran.
    assert conn.executed == []


@pytest.mark.asyncio
async def test_disable_plugin_allowed_when_dependent_exists_but_disabled(
    monkeypatch,
):
    plugin_id = str(uuid.uuid4())
    dependent_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    conn = _FakeConn(
        existing_row=existing,
        dep_rows=[_dep_installation_row(dependent_id, enabled=False)],
    )
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependents=[{"plugin_id": dependent_id, "name": "network"}])

    result = await management.disable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert result == {"status": "disabled", "plugin_id": plugin_id}


@pytest.mark.asyncio
async def test_disable_plugin_allowed_when_dependent_never_installed_by_this_user(
    monkeypatch,
):
    plugin_id = str(uuid.uuid4())
    dependent_id = str(uuid.uuid4())
    existing = _installation_row(plugin_id, enabled=True)
    # dependent_id has no row at all for this user -- can't be "still enabled".
    conn = _FakeConn(existing_row=existing, dep_rows=[])
    monkeypatch.setattr(management, "get_pool", AsyncMock(return_value=_FakePool(conn)))
    neo4j = _FakeNeo4j(dependents=[{"plugin_id": dependent_id, "name": "network"}])

    result = await management.disable_plugin(
        plugin_id=plugin_id, current_user={"sub": "4"}, neo4j=neo4j
    )

    assert result == {"status": "disabled", "plugin_id": plugin_id}
