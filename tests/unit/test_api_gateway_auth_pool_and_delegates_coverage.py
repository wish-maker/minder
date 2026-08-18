"""Unit tests filling api-gateway's core/auth.py's remaining coverage gaps (84%).

test_api_gateway_user_credentials.py already covers create_user/
verify_user_credentials's own logic, but always mocks get_pg_pool out via a
fake pool -- its own body (the actual create_pg_pool call + pool reuse) never
executed. close_pg_pool, init_users_table, create_user's generic
UniqueViolationError fallback branch (neither "username" nor "email" in the
message), and the three thin JWT delegates (create_jwt_token/
verify_jwt_token/get_current_user, which just forward to
shared.auth.jwt_middleware) were entirely untested.

Same auth_mod fixture (spec_from_file_location + fake config module) as
test_api_gateway_user_credentials.py.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import pytest

_AUTH_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "core"
    / "auth.py"
)


@pytest.fixture
def auth_mod():
    saved_config = sys.modules.get("config")
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        DB_HOST="db-host",
        DB_PORT=5432,
        DB_USER="minder",
        DB_PASSWORD="test",
        DB_NAME="minder_db",
    )
    sys.modules["config"] = cfg
    try:
        spec = importlib.util.spec_from_file_location("auth_under_test_3", _AUTH_MOD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        mod._pg_pool = None
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


# ── get_pg_pool / close_pg_pool ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pg_pool_creates_once_and_reuses(auth_mod, monkeypatch):
    # `from shared.db.pool import create_pg_pool` already bound the name directly
    # into auth_mod's own namespace at import time -- patching the source
    # shared.db.pool module's attribute afterward wouldn't reach it (same gotcha
    # as routes/auth.py's OIDC tests hit for fetch_userinfo).
    sentinel_pool = object()
    captured = {}

    async def fake_create_pg_pool(**kwargs):
        captured.update(kwargs)
        return sentinel_pool

    monkeypatch.setattr(auth_mod, "create_pg_pool", fake_create_pg_pool)

    first = await auth_mod.get_pg_pool()
    second = await auth_mod.get_pg_pool()

    assert first is sentinel_pool
    assert second is sentinel_pool
    assert captured["host"] == "db-host"
    assert captured["database"] == "minder_db"


@pytest.mark.asyncio
async def test_close_pg_pool_closes_and_resets(auth_mod):
    fake_pool = AsyncMock()
    auth_mod._pg_pool = fake_pool

    await auth_mod.close_pg_pool()

    fake_pool.close.assert_awaited_once()
    assert auth_mod._pg_pool is None


@pytest.mark.asyncio
async def test_close_pg_pool_is_a_noop_when_no_pool_exists(auth_mod):
    auth_mod._pg_pool = None

    await auth_mod.close_pg_pool()  # must not raise

    assert auth_mod._pg_pool is None


# ── init_users_table ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_init_users_table_applies_the_schema(auth_mod, monkeypatch):
    sentinel_pool = object()
    monkeypatch.setattr(auth_mod, "get_pg_pool", AsyncMock(return_value=sentinel_pool))
    apply_spy = AsyncMock()
    monkeypatch.setattr(auth_mod, "apply_schema", apply_spy)

    await auth_mod.init_users_table()

    apply_spy.assert_awaited_once_with(sentinel_pool, auth_mod._SCHEMA_PATH)


# ── create_user: generic conflict fallback ────────────────────────────────────


class _BoomConn:
    def __init__(self, error):
        self._error = error

    async def fetchrow(self, query, *args):
        raise self._error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _BoomPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return self._conn


@pytest.mark.asyncio
async def test_create_user_generic_conflict_when_message_names_neither_field(
    auth_mod, monkeypatch
):
    error = asyncpg.UniqueViolationError("duplicate key value violates constraint")
    conn = _BoomConn(error)
    monkeypatch.setattr(
        auth_mod, "get_pg_pool", AsyncMock(return_value=_BoomPool(conn))
    )

    with pytest.raises(Exception) as exc_info:
        await auth_mod.create_user("alice", "alice@x.com", "password123")

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "User already exists"


# ── thin JWT delegates: forward to shared.auth.jwt_middleware ────────────────


def test_create_jwt_token_delegates_to_shared_jwt_middleware(auth_mod, monkeypatch):
    captured = {}

    def fake_create(data):
        captured["data"] = data
        return "signed.jwt.token"

    monkeypatch.setattr(auth_mod.jwt_middleware, "create_jwt_token", fake_create)

    result = auth_mod.create_jwt_token({"sub": "1"})

    assert result == "signed.jwt.token"
    assert captured["data"] == {"sub": "1"}


def test_verify_jwt_token_delegates_to_shared_jwt_middleware(auth_mod, monkeypatch):
    monkeypatch.setattr(
        auth_mod.jwt_middleware,
        "verify_jwt_token",
        lambda token: {"sub": "1", "t": token},
    )

    result = auth_mod.verify_jwt_token("some.jwt.token")

    assert result == {"sub": "1", "t": "some.jwt.token"}


@pytest.mark.asyncio
async def test_get_current_user_delegates_to_the_optional_shared_dependency(
    auth_mod, monkeypatch
):
    async def fake_optional(request):
        return {"sub": "1"} if request == "req" else None

    monkeypatch.setattr(
        auth_mod.jwt_middleware, "get_current_user_optional", fake_optional
    )

    result = await auth_mod.get_current_user("req")

    assert result == {"sub": "1"}


@pytest.mark.asyncio
async def test_get_current_user_required_delegates_to_the_raising_shared_dependency(
    auth_mod, monkeypatch
):
    async def fake_required(request):
        return {"sub": "1", "required": True}

    monkeypatch.setattr(auth_mod.jwt_middleware, "get_current_user", fake_required)

    result = await auth_mod.get_current_user_required("req")

    assert result == {"sub": "1", "required": True}
