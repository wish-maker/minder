"""Unit tests for api-gateway's core/auth.py -- create_user and
verify_user_credentials, which had zero direct tests (only ever mocked out
when testing routes/auth.py's register/login endpoints, per
test_oidc_routes.py). 105-132/148-178 uncovered per `coverage run`.

Reuses test_oidc_user_provisioning.py's fake-asyncpg-pool pattern exactly
(same fixture shape, same fresh-import-with-fake-config precedent) since
create_user/verify_user_credentials live in the same module and share the
same isolation needs.

Also characterizes (does NOT endorse) the current pre-authentication
account-state leak tracked in #717 (decision issue: #758): verify_user_credentials checks
`is_active` BEFORE the bcrypt password check, so a disabled account gets a
distinct 403 regardless of the password supplied, while a wrong password on
an active account returns a generic None. That is a real, filed, decision-
gated issue (whether a disabled account should get a distinct message at
all is a UX tradeoff, not a bug to silently "fix" here) -- these tests only
document what verify_user_credentials actually does today, so a future fix
has a concrete baseline to change deliberately.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import asyncpg
import pytest
from bcrypt import gensalt, hashpw
from fastapi import HTTPException

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
        spec = importlib.util.spec_from_file_location("auth_under_test_2", _AUTH_MOD)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


class _ScriptedConn:
    def __init__(self, responses=None, raises=None):
        self._responses = {k: list(v) for k, v in (responses or {}).items()}
        self._raises = raises
        self.calls = []

    async def fetchrow(self, query, *args):
        self.calls.append((query, args))
        if self._raises:
            raise self._raises
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
    async def _fake_get_pool():
        return _ScriptedPool(conn)

    monkeypatch.setattr(auth_mod, "get_pg_pool", _fake_get_pool)


# --- create_user -------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_user_hashes_the_password_and_forces_role_user(
    auth_mod, monkeypatch
):
    inserted_args = {}

    class _Conn:
        async def fetchrow(self, query, *args):
            (
                inserted_args["username"],
                inserted_args["email"],
                inserted_args["hash"],
            ) = args
            return {
                "id": 1,
                "username": args[0],
                "email": args[1],
                "role": "user",
                "is_active": True,
                "created_at": "2026-01-01",
            }

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    class _Pool:
        def acquire(self):
            return _Conn()

    async def _fake_get_pool():
        return _Pool()

    monkeypatch.setattr(auth_mod, "get_pg_pool", _fake_get_pool)

    result = await auth_mod.create_user("alice", "alice@x.com", "hunter2")

    assert result["username"] == "alice"
    assert result["role"] == "user"
    # The plaintext password is never inserted -- only a bcrypt hash, and that
    # hash actually verifies against the original password.
    assert inserted_args["hash"] != "hunter2"
    from bcrypt import checkpw

    assert checkpw(b"hunter2", inserted_args["hash"].encode("utf-8"))


@pytest.mark.asyncio
async def test_create_user_duplicate_username_is_409(auth_mod, monkeypatch):
    conn = _ScriptedConn(
        raises=asyncpg.UniqueViolationError(
            'duplicate key value violates unique constraint "users_username_key"'
        )
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    with pytest.raises(HTTPException) as exc_info:
        await auth_mod.create_user("alice", "alice@x.com", "hunter2")
    assert exc_info.value.status_code == 409
    assert "Username" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_user_duplicate_email_is_409(auth_mod, monkeypatch):
    conn = _ScriptedConn(
        raises=asyncpg.UniqueViolationError(
            'duplicate key value violates unique constraint "users_email_key"'
        )
    )
    _patch_pool(monkeypatch, auth_mod, conn)

    with pytest.raises(HTTPException) as exc_info:
        await auth_mod.create_user("alice", "alice@x.com", "hunter2")
    assert exc_info.value.status_code == 409
    assert "Email" in exc_info.value.detail


# --- verify_user_credentials --------------------------------------------------


def _user_row(password, is_active=True, **overrides):
    row = {
        "id": 1,
        "username": "alice",
        "email": "alice@x.com",
        "password_hash": hashpw(password.encode("utf-8"), gensalt()).decode("utf-8"),
        "role": "user",
        "is_active": is_active,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_unknown_username_returns_none(auth_mod, monkeypatch):
    conn = _ScriptedConn({"WHERE username = $1": [None]})
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.verify_user_credentials("nobody", "whatever")

    assert result is None


@pytest.mark.asyncio
async def test_correct_password_returns_user_without_the_hash(auth_mod, monkeypatch):
    row = _user_row("hunter2")
    conn = _ScriptedConn({"WHERE username = $1": [row]})
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.verify_user_credentials("alice", "hunter2")

    assert result["username"] == "alice"
    assert "password_hash" not in result


@pytest.mark.asyncio
async def test_wrong_password_on_an_active_account_returns_none(auth_mod, monkeypatch):
    row = _user_row("hunter2")
    conn = _ScriptedConn({"WHERE username = $1": [row]})
    _patch_pool(monkeypatch, auth_mod, conn)

    result = await auth_mod.verify_user_credentials("alice", "wrong-password")

    assert result is None


@pytest.mark.asyncio
async def test_characterizes_the_717_leak_disabled_account_403_regardless_of_password(
    auth_mod, monkeypatch
):
    """Documents #717's current (pre-decision, see #758) behavior: ANY
    password for a disabled account raises a distinct 403 -- the exact
    opposite of the generic None a wrong password gets on an active account
    (see the test above). This is what makes the account state enumerable
    pre-auth. Not an endorsement -- update this test if/when #717/#758 is
    resolved."""
    row = _user_row("hunter2", is_active=False)
    conn = _ScriptedConn({"WHERE username = $1": [row]})
    _patch_pool(monkeypatch, auth_mod, conn)

    with pytest.raises(HTTPException) as exc_info:
        await auth_mod.verify_user_credentials("alice", "totally-wrong-password")

    assert exc_info.value.status_code == 403
    assert "disabled" in exc_info.value.detail.lower()
