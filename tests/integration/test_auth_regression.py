"""
Regression tests for API Gateway authentication.

Guards the clean-install auth bug fixed on 2026-07-10: the `users` table was
created in an `@app.on_event("startup")` handler, which FastAPI silently ignores
when a `lifespan` handler is set. The table was therefore never created and
register/login failed with `relation "users" does not exist`. Table
initialization now runs inside `lifespan`.

These tests run against the live API Gateway (http://localhost:8000). They are
skipped automatically if the gateway is not reachable, so they never hang.
"""

import os

import httpx
import pytest

GATEWAY = os.environ.get("MINDER_GATEWAY_URL", "http://localhost:8000")
TIMEOUT = 8.0


def _gateway_up() -> bool:
    try:
        r = httpx.get(f"{GATEWAY}/health", timeout=3.0)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _gateway_up(), reason="API Gateway not reachable on localhost:8000"
    ),
]


@pytest.fixture(scope="module")
def credentials():
    # Unique per run so re-runs don't collide on the UNIQUE username/email.
    suffix = os.getpid()
    return {
        "username": f"reg_{suffix}",
        "email": f"reg_{suffix}@example.com",
        "password": "Regress123!",
    }


def test_health_reports_healthy():
    r = httpx.get(f"{GATEWAY}/health", timeout=TIMEOUT)
    assert r.status_code == 200
    assert r.json().get("status") == "healthy"


def test_register_creates_user(credentials):
    r = httpx.post(f"{GATEWAY}/v1/auth/register", json=credentials, timeout=TIMEOUT)
    # 200/201 on first create; 400/409 if a previous run already created it.
    assert r.status_code in (200, 201, 400, 409), r.text
    if r.status_code in (200, 201):
        body = r.json()
        assert body["user"]["username"] == credentials["username"]


def test_login_returns_jwt(credentials):
    # Ensure the user exists (idempotent).
    httpx.post(f"{GATEWAY}/v1/auth/register", json=credentials, timeout=TIMEOUT)

    r = httpx.post(
        f"{GATEWAY}/v1/auth/login",
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


def test_login_rejects_bad_password(credentials):
    httpx.post(f"{GATEWAY}/v1/auth/register", json=credentials, timeout=TIMEOUT)
    r = httpx.post(
        f"{GATEWAY}/v1/auth/login",
        json={"username": credentials["username"], "password": "wrong-password"},
        timeout=TIMEOUT,
    )
    assert r.status_code in (401, 403), r.text
