"""Unit tests for shared/auth/jwt_middleware.py -- create_jwt_token,
verify_jwt_token, get_current_user(_optional/_or_service), and the
require_role(_or_service) dependency factories.

This shared module backs auth for EVERY service in the platform, but had no
dedicated test file of its own -- only ever imported/mocked as a dependency
in other services' route tests. shared.auth.jwt_middleware is a real,
stable top-level package (no hyphenated-service collision risk), so it's
imported directly with no isolation gymnastics.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import shared.auth.jwt_middleware as jwt_mw

# --- create_jwt_token / verify_jwt_token ------------------------------------


def test_create_and_verify_round_trips_the_payload():
    token = jwt_mw.create_jwt_token({"sub": "u1", "username": "alice", "role": "user"})

    payload = jwt_mw.verify_jwt_token(token)

    assert payload["sub"] == "u1"
    assert payload["username"] == "alice"
    assert payload["role"] == "user"
    assert "exp" in payload


def test_verify_rejects_a_garbage_token():
    with pytest.raises(HTTPException) as exc_info:
        jwt_mw.verify_jwt_token("not-a-real-jwt")
    assert exc_info.value.status_code == 401
    assert "Invalid token" in exc_info.value.detail


def test_verify_rejects_an_expired_token(monkeypatch):
    monkeypatch.setattr(jwt_mw, "JWT_EXPIRATION_MINUTES", -1)
    expired_token = jwt_mw.create_jwt_token({"sub": "u1"})

    with pytest.raises(HTTPException) as exc_info:
        jwt_mw.verify_jwt_token(expired_token)
    assert exc_info.value.status_code == 401
    assert "expired" in exc_info.value.detail.lower()


def test_verify_rejects_a_token_signed_with_a_different_secret():
    from jose import jwt as jose_jwt

    token = jose_jwt.encode(
        {"sub": "u1"}, "a-totally-different-secret", algorithm="HS256"
    )

    with pytest.raises(HTTPException) as exc_info:
        jwt_mw.verify_jwt_token(token)
    assert exc_info.value.status_code == 401


# --- get_current_user --------------------------------------------------------


def _request_with(auth_header=None):
    headers = {"Authorization": auth_header} if auth_header else {}
    return SimpleNamespace(headers=headers)


@pytest.mark.asyncio
async def test_get_current_user_rejects_a_missing_header():
    with pytest.raises(HTTPException) as exc_info:
        await jwt_mw.get_current_user(_request_with())
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_a_non_bearer_scheme():
    with pytest.raises(HTTPException) as exc_info:
        await jwt_mw.get_current_user(_request_with("Basic dXNlcjpwYXNz"))
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_returns_the_payload_for_a_valid_token():
    token = jwt_mw.create_jwt_token({"sub": "u1", "role": "admin"})

    payload = await jwt_mw.get_current_user(_request_with(f"Bearer {token}"))

    assert payload["sub"] == "u1"
    assert payload["role"] == "admin"


# --- get_current_user_optional ----------------------------------------------


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_none_without_raising():
    result = await jwt_mw.get_current_user_optional(_request_with())
    assert result is None


@pytest.mark.asyncio
async def test_get_current_user_optional_returns_the_payload_when_valid():
    token = jwt_mw.create_jwt_token({"sub": "u1"})
    result = await jwt_mw.get_current_user_optional(_request_with(f"Bearer {token}"))
    assert result["sub"] == "u1"


# --- get_current_user_or_service --------------------------------------------


@pytest.mark.asyncio
async def test_service_token_is_accepted_when_configured(monkeypatch):
    monkeypatch.setattr(jwt_mw, "SERVICE_SYNC_TOKEN", "shared-secret")
    request = SimpleNamespace(headers={"X-Service-Token": "shared-secret"})

    result = await jwt_mw.get_current_user_or_service(request)

    assert result["role"] == "service"


@pytest.mark.asyncio
async def test_wrong_service_token_falls_back_to_user_jwt_and_401s(monkeypatch):
    monkeypatch.setattr(jwt_mw, "SERVICE_SYNC_TOKEN", "shared-secret")
    request = SimpleNamespace(headers={"X-Service-Token": "wrong-guess"})

    with pytest.raises(HTTPException) as exc_info:
        await jwt_mw.get_current_user_or_service(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_service_token_never_accepted_when_unset(monkeypatch):
    monkeypatch.setattr(jwt_mw, "SERVICE_SYNC_TOKEN", None)
    # Even a caller who somehow guesses the literal string "None" must not
    # get in when the feature itself is disabled.
    request = SimpleNamespace(headers={"X-Service-Token": "None"})

    with pytest.raises(HTTPException) as exc_info:
        await jwt_mw.get_current_user_or_service(request)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_falls_back_to_a_valid_user_jwt_when_no_service_token_given(
    monkeypatch,
):
    monkeypatch.setattr(jwt_mw, "SERVICE_SYNC_TOKEN", "shared-secret")
    token = jwt_mw.create_jwt_token({"sub": "u1", "role": "user"})
    request = SimpleNamespace(headers={"Authorization": f"Bearer {token}"})

    result = await jwt_mw.get_current_user_or_service(request)

    assert result["sub"] == "u1"


# --- require_role / require_role_or_service ---------------------------------


@pytest.mark.asyncio
async def test_require_role_rejects_the_wrong_role():
    dependency = jwt_mw.require_role("admin")

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user={"role": "user"})
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_require_role_passes_the_matching_role():
    dependency = jwt_mw.require_role("admin", "superadmin")

    result = await dependency(user={"role": "superadmin"})

    assert result == {"role": "superadmin"}


@pytest.mark.asyncio
async def test_require_role_or_service_lets_the_service_principal_through_any_role():
    dependency = jwt_mw.require_role_or_service("admin")

    result = await dependency(user={"role": "service"})

    assert result == {"role": "service"}


@pytest.mark.asyncio
async def test_require_role_or_service_still_checks_role_for_real_users():
    dependency = jwt_mw.require_role_or_service("admin")

    with pytest.raises(HTTPException) as exc_info:
        await dependency(user={"role": "user"})
    assert exc_info.value.status_code == 403
