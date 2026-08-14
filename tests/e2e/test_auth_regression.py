"""
Regression tests for API Gateway authentication, run against the real
live-process harness (`live_stack`, #437 -- moved here from tests/integration/
so these actually execute in CI instead of silently skipping for lack of a
network-reachable service).

Guards the clean-install auth bug fixed on 2026-07-10: the `users` table was
created in an `@app.on_event("startup")` handler, which FastAPI silently ignores
when a `lifespan` handler is set. The table was therefore never created and
register/login failed with `relation "users" does not exist`. Table
initialization now runs inside `lifespan`.

Also guards the privilege-escalation bug fixed for #474: `RegisterRequest` used
to accept a caller-controlled `role` field and pass it straight through to
`create_user`, so anyone could `POST /v1/auth/register` with `"role": "admin"`
and get a real admin JWT back. Every self-registered account is now forced to
`role="user"` -- admin is only ever granted via Authelia OIDC group membership.
"""

import os
import uuid

import httpx
import pytest

TIMEOUT = 8.0


@pytest.fixture
def credentials():
    # Unique per test so re-runs don't collide on the UNIQUE username/email.
    # uuid4, not id(object()) -- CPython can recycle a garbage-collected
    # object's id() within the same process, which would silently produce
    # colliding usernames across different tests (see #437's marketplace
    # plugin_id fixture fix for the same class of bug with os.getpid() alone).
    suffix = f"{os.getpid()}_{uuid.uuid4().hex[:8]}"
    return {
        "username": f"reg_{suffix}",
        "email": f"reg_{suffix}@example.com",
        "password": "Regress123!",
    }


def test_health_reports_healthy(live_stack):
    r = httpx.get(f"{live_stack.gateway_url}/health", timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json().get("status") == "healthy"


def test_register_creates_user(live_stack, credentials):
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register", json=credentials, timeout=TIMEOUT
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["username"] == credentials["username"]


def test_register_ignores_caller_supplied_role(live_stack, credentials):
    """#474: a caller-supplied "role" must never reach the created account --
    admin is only granted via Authelia OIDC group membership, never through
    self-registration."""
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register",
        json={**credentials, "role": "admin"},
        timeout=TIMEOUT,
    )
    assert r.status_code == 201, r.text
    assert r.json()["user"]["role"] == "user"

    login = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={"username": credentials["username"], "password": credentials["password"]},
        timeout=TIMEOUT,
    )
    assert login.status_code == 200, login.text
    assert login.json()["user"]["role"] == "user"


def test_login_returns_jwt(live_stack, credentials):
    httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register", json=credentials, timeout=TIMEOUT
    )

    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={
            "username": credentials["username"],
            "password": credentials["password"],
        },
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("token_type") == "bearer"
    assert body.get("access_token"), "missing access_token"


def test_login_rejects_bad_password(live_stack, credentials):
    httpx.post(
        f"{live_stack.gateway_url}/v1/auth/register", json=credentials, timeout=TIMEOUT
    )
    r = httpx.post(
        f"{live_stack.gateway_url}/v1/auth/login",
        json={"username": credentials["username"], "password": "wrong-password"},
        timeout=TIMEOUT,
    )
    assert r.status_code in (401, 403), r.text
