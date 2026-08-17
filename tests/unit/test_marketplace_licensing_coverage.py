"""Unit tests filling licensing.py's remaining coverage gaps (77%).

The sibling suites already cover create_license's no-conflict/existing/retry-
after-one-conflict paths and validate_license's expired/future/perpetual
paths. This adds: create_license's persistent-conflict branch (both attempts
hit UniqueViolationError -- the retry budget is genuinely exhausted, not just
retried once), validate_license's not-found branch, and get_user_licenses
(entirely untested) -- including its ISO-format-or-None handling for
valid_until/last_used_at.

Same module-loading pattern as test_marketplace_create_license_race.py
(duplicated per that file's own stated convention for this module).
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
    "_marketplace_licensing_coverage_under_test",
    _MARKETPLACE_DIR / "core" / "licensing.py",
)
licensing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = licensing
_spec.loader.exec_module(licensing)


class _FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


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


# --- create_license: persistent conflict past both retry attempts -----------


class _AlwaysConflictConn:
    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        q = " ".join(query.split())
        if q.startswith("SELECT * FROM marketplace_licenses"):
            return None
        if q.startswith("INSERT INTO marketplace_licenses"):
            raise asyncpg.UniqueViolationError("duplicate active license")
        return None

    async def execute(self, query, *args):
        pass


@pytest.mark.asyncio
async def test_create_license_raises_after_persistent_conflict(patch_pool):
    """Both attempts hit UniqueViolationError -- the retry budget (2 attempts)
    is genuinely exhausted, so the second failure must propagate, not retry
    forever or silently swallow the conflict."""
    patch_pool(_AlwaysConflictConn())

    with pytest.raises(asyncpg.UniqueViolationError):
        await licensing.create_license(
            user_id="user-1", plugin_id="plugin-1", tier="pro"
        )


# --- validate_license: not found ----------------------------------------------


class _NoRowConn:
    def transaction(self):
        return _FakeTransaction()

    async def fetchrow(self, query, *args):
        return None

    async def execute(self, query, *args):
        pass


@pytest.mark.asyncio
async def test_validate_license_not_found_or_inactive(patch_pool):
    patch_pool(_NoRowConn())

    result = await licensing.validate_license("bad-key", "plugin-1")

    assert result == {"valid": False, "reason": "License not found or inactive"}


# --- get_user_licenses ---------------------------------------------------------


class _FetchConn:
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, query, *args):
        return self._rows


def _license_row(**overrides):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    row = {
        "id": "license-1",
        "user_id": "user-1",
        "plugin_id": "plugin-1",
        "tier": "pro",
        "license_key": "key-abc",
        "valid_from": now,
        "valid_until": now,
        "active": True,
        "usage_count": 3,
        "last_used_at": now,
        "plugin_name": "weather",
        "plugin_display_name": "Weather",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_get_user_licenses_returns_serialized_list(patch_pool):
    row = _license_row()
    patch_pool(_FetchConn([row]))

    result = await licensing.get_user_licenses("user-1")

    assert len(result) == 1
    entry = result[0]
    assert entry["id"] == "license-1"
    assert entry["plugin_name"] == "weather"
    assert entry["valid_from"] == row["valid_from"].isoformat()
    assert entry["valid_until"] == row["valid_until"].isoformat()
    assert entry["last_used_at"] == row["last_used_at"].isoformat()
    assert entry["usage_count"] == 3


@pytest.mark.asyncio
async def test_get_user_licenses_handles_null_valid_until_and_last_used(patch_pool):
    row = _license_row(valid_until=None, last_used_at=None)
    patch_pool(_FetchConn([row]))

    result = await licensing.get_user_licenses("user-1")

    assert result[0]["valid_until"] is None
    assert result[0]["last_used_at"] is None


@pytest.mark.asyncio
async def test_get_user_licenses_empty_when_no_rows(patch_pool):
    patch_pool(_FetchConn([]))

    result = await licensing.get_user_licenses("user-1")

    assert result == []
