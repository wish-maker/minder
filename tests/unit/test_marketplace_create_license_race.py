"""Unit tests for marketplace's create_license() concurrent-activation race fix.

create_license() does a check-then-write (SELECT for an existing active license,
then UPDATE or INSERT) that used to run with no transaction and no DB-level
constraint stopping two concurrent activate calls for the same user+plugin from
both passing the SELECT and both INSERTing -- marketplace_licenses only has a
unique constraint on license_key, not on (user_id, plugin_id, active). The fix
adds a partial unique index (schema.sql) plus a retry: the loser's INSERT now
raises asyncpg.UniqueViolationError, which create_license() catches and retries,
taking the UPDATE branch against the winner's now-visible row.

DB-free: get_pool is monkeypatched with a fake pool/conn, same pattern as
test_marketplace_licensing_expiry.py. That file's module-loading boilerplate is
duplicated here rather than shared, matching this test suite's existing
per-file convention for marketplace's core/licensing.py.
"""

import importlib.util
import sys
from pathlib import Path

import asyncpg
import pytest

_MARKETPLACE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
)
sys.path.insert(0, str(_MARKETPLACE_DIR))
for _stale in list(sys.modules):
    if _stale == "core" or _stale.startswith("core.") or _stale == "config":
        del sys.modules[_stale]

_spec = importlib.util.spec_from_file_location(
    "_marketplace_licensing_race_under_test", _MARKETPLACE_DIR / "core" / "licensing.py"
)
licensing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = licensing
_spec.loader.exec_module(licensing)


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    """Routes on SQL text; `select_results` is popped once per SELECT so each
    retry attempt can see a different world (no existing row, then a row that
    "appeared" underneath us)."""

    def __init__(self, select_results):
        self._select_results = list(select_results)
        self.insert_attempts = 0
        self.updates = []

    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if q.startswith("SELECT * FROM marketplace_licenses"):
            return self._select_results.pop(0)
        if q.startswith("INSERT INTO marketplace_licenses"):
            self.insert_attempts += 1
            if self.insert_attempts == 1 and self._force_conflict:
                raise asyncpg.UniqueViolationError("duplicate active license")
            user_id, plugin_id, tier, license_key, valid_until = args
            return {
                "id": "new-license-id",
                "user_id": user_id,
                "plugin_id": plugin_id,
                "tier": tier,
                "license_key": license_key,
                "valid_from": None,
                "valid_until": valid_until,
                "created_at": None,
            }
        return None

    async def execute(self, query, *args):
        self.updates.append(args)


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


@pytest.fixture
def patch_pool(monkeypatch):
    def _install(conn):
        async def _get_pool():
            return _FakePool(conn)

        monkeypatch.setattr(licensing, "get_pool", _get_pool)
        return conn

    return _install


async def test_create_license_no_conflict_inserts_once(patch_pool):
    conn = _FakeConn(select_results=[None])
    conn._force_conflict = False
    patch_pool(conn)

    result = await licensing.create_license(
        user_id="user-1", plugin_id="plugin-1", tier="pro"
    )

    assert result["active"] is True
    assert conn.insert_attempts == 1
    assert conn.updates == []


async def test_create_license_retries_as_update_after_unique_violation(patch_pool):
    """The race this fix targets: attempt 1's SELECT sees no active license, but
    its INSERT loses to a concurrent winner and gets UniqueViolationError.
    Attempt 2's SELECT now sees the winner's row and must UPDATE it, not raise."""
    winner_row = {
        "id": "winner-license-id",
        "user_id": "user-1",
        "plugin_id": "plugin-1",
        "valid_from": None,
    }
    conn = _FakeConn(select_results=[None, winner_row])
    conn._force_conflict = True
    patch_pool(conn)

    result = await licensing.create_license(
        user_id="user-1", plugin_id="plugin-1", tier="pro"
    )

    assert result["id"] == "winner-license-id"
    assert result["active"] is True
    assert conn.insert_attempts == 1  # the 2nd attempt took the UPDATE branch
    assert len(conn.updates) == 1


async def test_create_license_existing_active_license_updates_in_place(patch_pool):
    existing_row = {
        "id": "existing-license-id",
        "user_id": "user-1",
        "plugin_id": "plugin-1",
        "valid_from": None,
    }
    conn = _FakeConn(select_results=[existing_row])
    conn._force_conflict = False
    patch_pool(conn)

    result = await licensing.create_license(
        user_id="user-1", plugin_id="plugin-1", tier="enterprise"
    )

    assert result["id"] == "existing-license-id"
    assert result["tier"] == "enterprise"
    assert conn.insert_attempts == 0
    assert len(conn.updates) == 1
