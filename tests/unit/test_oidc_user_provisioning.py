"""Unit tests for api-gateway's OIDC user provisioning (core/auth.py's
get_or_create_oidc_user, #<issue>).

Covers the three lookup branches described in the function's own docstring --
already-linked (unchanged / drifted / collides-on-sync), pre-existing local
account (linked by username), and brand new (provisioned / collides-and-
suffixed) -- against a scripted fake asyncpg pool. No real database.

api-gateway is a hyphenated service dir; auth.py imports ``from config import
settings`` at module top -- faked and restored, matching test_gateway_tool_args.py.
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
    cfg.settings = SimpleNamespace()
    sys.modules["config"] = cfg
    try:
        spec = importlib.util.spec_from_file_location("auth_under_test", _AUTH_MOD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


class _ScriptedConn:
    """Dispatches fetchrow() by matching a distinctive substring of the query
    text to a queue of scripted results (or exceptions), consumed in order.
    One queue per substring -- get_or_create_oidc_user never issues the same
    distinct query text twice within a branch, except the INSERT retry path,
    which is exactly why the results are a per-key *queue* and not a single
    value."""

    def __init__(self, responses):
        self._responses = {k: list(v) for k, v in responses.items()}
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        for key, results in self._responses.items():
            if key in query:
                if not results:
                    raise AssertionError(f"no more scripted responses for {key!r}")
                result = results.pop(0)
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"unscripted query: {query}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _ScriptedAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _ScriptedPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        return _ScriptedAcquire(self._conn)


def _patch_pool(monkeypatch, auth_mod, conn):
    monkeypatch.setattr(
        auth_mod, "get_pg_pool", AsyncMock(return_value=_ScriptedPool(conn))
    )


# ── Branch 1: already linked to this authelia_subject ──────────────────────


@pytest.mark.asyncio
async def test_linked_user_unchanged_returns_row_without_extra_calls(
    auth_mod, monkeypatch
):
    row = {"id": 1, "username": "alice", "email": "alice@x.com", "role": "user"}
    conn = _ScriptedConn({"WHERE authelia_subject = $1": [row]})
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user("sub-1", "alice", "alice@x.com", [])

    assert result == row
    assert len(conn.calls) == 1


@pytest.mark.asyncio
async def test_linked_user_drifted_profile_is_synced(auth_mod, monkeypatch):
    old_row = {"id": 1, "username": "olduuid", "email": "old@x.com", "role": "user"}
    updated_row = {"id": 1, "username": "alice", "email": "alice@x.com", "role": "user"}
    conn = _ScriptedConn(
        {
            "WHERE authelia_subject = $1": [old_row],
            "UPDATE users SET username = $1, email = $2, role = $3": [updated_row],
        }
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user("sub-1", "alice", "alice@x.com", [])

    assert result == updated_row


@pytest.mark.asyncio
async def test_linked_user_sync_collision_keeps_old_row(auth_mod, monkeypatch):
    old_row = {"id": 1, "username": "olduuid", "email": "old@x.com", "role": "user"}
    conn = _ScriptedConn(
        {
            "WHERE authelia_subject = $1": [old_row],
            "UPDATE users SET username = $1, email = $2, role = $3": [
                asyncpg.UniqueViolationError()
            ],
        }
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user("sub-1", "alice", "alice@x.com", [])

    assert result == old_row


@pytest.mark.asyncio
async def test_linked_user_role_promoted_from_admins_group(auth_mod, monkeypatch):
    old_row = {"id": 1, "username": "alice", "email": "alice@x.com", "role": "user"}
    updated_row = {
        "id": 1,
        "username": "alice",
        "email": "alice@x.com",
        "role": "admin",
    }
    conn = _ScriptedConn(
        {
            "WHERE authelia_subject = $1": [old_row],
            "UPDATE users SET username = $1, email = $2, role = $3": [updated_row],
        }
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user(
        "sub-1", "alice", "alice@x.com", ["admins"]
    )

    assert result["role"] == "admin"


# ── Branch 2: pre-existing local account, linked by username ───────────────


@pytest.mark.asyncio
async def test_preexisting_local_account_gets_linked(auth_mod, monkeypatch):
    existing_row = {"id": 2, "username": "bob", "email": "bob@x.com", "role": "user"}
    linked_row = {"id": 2, "username": "bob", "email": "bob@x.com", "role": "user"}
    conn = _ScriptedConn(
        {
            "WHERE authelia_subject = $1": [None],
            "WHERE username = $1 AND authelia_subject IS NULL": [existing_row],
            "UPDATE users SET authelia_subject = $1": [linked_row],
        }
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user("sub-2", "bob", "bob@x.com", [])

    assert result == linked_row


# ── Branch 3: brand new user ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_brand_new_user_is_provisioned(auth_mod, monkeypatch):
    new_row = {"id": 3, "username": "carol", "email": "carol@x.com", "role": "admin"}
    conn = _ScriptedConn(
        {
            "WHERE authelia_subject = $1": [None],
            "WHERE username = $1 AND authelia_subject IS NULL": [None],
            "INSERT INTO users (username, email, password_hash, role, authelia_subject)": [
                new_row
            ],
        }
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user(
        "sub-3", "carol", "carol@x.com", ["admins"]
    )

    assert result == new_row


@pytest.mark.asyncio
async def test_brand_new_user_insert_collision_retries_with_suffixed_username(
    auth_mod, monkeypatch
):
    suffixed_row = {
        "id": 4,
        "username": "dave-sub-4",
        "email": "sub-4@authelia.minder.local",
        "role": "user",
    }
    conn = _ScriptedConn(
        {
            "WHERE authelia_subject = $1": [None],
            "WHERE username = $1 AND authelia_subject IS NULL": [None],
            "INSERT INTO users (username, email, password_hash, role, authelia_subject)": [
                asyncpg.UniqueViolationError(),
                suffixed_row,
            ],
        }
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.get_or_create_oidc_user("sub-4", "dave", "dave@x.com", [])

    assert result == suffixed_row
    insert_calls = [c for c in conn.calls if "INSERT INTO users" in c[0]]
    assert len(insert_calls) == 2
    second_args = insert_calls[1][1]
    assert second_args[0] == "dave-sub-4"
    assert second_args[1] == "sub-4@authelia.minder.local"
