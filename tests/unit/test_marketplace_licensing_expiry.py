"""Unit tests for marketplace license expiry comparison (#223 item 6).

`marketplace_licenses.valid_until` is a naive `TIMESTAMP` column, so asyncpg returns
a naive datetime. `validate_license` must compare it against a naive-UTC now() — a
tz-aware now() would raise "can't compare offset-naive and offset-aware datetimes".
These lock that: an expired license reports expired (no TypeError), a future one
validates.

DB-free: `get_pool` is monkeypatched with a fake pool/conn.

Loaded by path (#266): licensing.py does `from core.database import get_pool`
(marketplace's own bare-import convention, matching every other service).
conftest.py loads every service's main.py into this ONE shared test process, so
a generic `core`/`config` module from an earlier-loaded service can already be
cached in sys.modules by the time this file collects — stale-clear those slots
and prepend marketplace's own dir so `core.database` resolves here.
"""

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_MARKETPLACE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
)
sys.path.insert(0, str(_MARKETPLACE_DIR))
for _stale in list(sys.modules):
    if _stale == "core" or _stale.startswith("core.") or _stale == "config":
        del sys.modules[_stale]

_spec = importlib.util.spec_from_file_location(
    "_marketplace_licensing_under_test", _MARKETPLACE_DIR / "core" / "licensing.py"
)
licensing = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = licensing
_spec.loader.exec_module(licensing)

# What a naive TIMESTAMP column round-trips as (asyncpg gives naive datetimes).
_NAIVE_NOW = datetime.now(timezone.utc).replace(tzinfo=None)


class _FakeConn:
    def __init__(self, row):
        self._row = row
        self.executed = False

    async def fetchrow(self, *args, **kwargs):
        return self._row

    async def execute(self, *args, **kwargs):
        self.executed = True


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
    """Install a fake pool returning `row` from fetchrow; hand back the conn."""

    def _install(row):
        conn = _FakeConn(row)

        async def _get_pool():
            return _FakePool(conn)

        monkeypatch.setattr(licensing, "get_pool", _get_pool)
        return conn

    return _install


def _row(valid_until):
    return {
        "id": "lic-1",
        "user_id": "user-1",
        "plugin_id": "plugin-1",
        "tier": "pro",
        "license_key": "AAAA-BBBB-CCCC-DDDD",
        "valid_until": valid_until,
        "usage_count": 4,
    }


async def test_expired_license_reports_expired_without_typeerror(patch_pool):
    conn = patch_pool(_row(_NAIVE_NOW - timedelta(days=1)))  # naive, in the past
    result = await licensing.validate_license("AAAA-BBBB-CCCC-DDDD", "plugin-1")
    assert result["valid"] is False
    assert result["reason"] == "License expired"
    assert conn.executed is False  # short-circuits before the usage bump


async def test_future_license_validates_and_bumps_usage(patch_pool):
    conn = patch_pool(_row(_NAIVE_NOW + timedelta(days=30)))  # naive, in the future
    result = await licensing.validate_license("AAAA-BBBB-CCCC-DDDD", "plugin-1")
    assert result["valid"] is True
    assert result["usage_count"] == 5
    assert conn.executed is True


async def test_perpetual_license_null_valid_until_validates(patch_pool):
    patch_pool(_row(None))
    result = await licensing.validate_license("AAAA-BBBB-CCCC-DDDD", "plugin-1")
    assert result["valid"] is True
    assert result["valid_until"] is None
