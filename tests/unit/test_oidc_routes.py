"""Unit tests for api-gateway's OIDC login/callback routes (routes/auth.py's
oidc_login / oidc_callback, #<issue>).

core.auth / core.oidc are faked wholesale (they have their own dedicated unit
tests -- test_oidc_user_provisioning.py / test_oidc_client.py) so these tests
exercise only routes/auth.py's own logic: state/nonce cookie round-tripping,
error/state validation, and building the client redirect. Matches the
sys.modules-faking pattern in test_gateway_proxy_headers.py.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "auth.py"
)


class _FakeRequest:
    def __init__(self, cookies=None):
        self.cookies = cookies or {}


@pytest.fixture
def auth_route_mod():
    names = ("core", "core.auth", "core.oidc")
    saved = {n: sys.modules.get(n) for n in names}
    for n in names:
        sys.modules[n] = ModuleType(n)
    sys.modules["core.auth"].create_jwt_token = lambda data: "signed.jwt.token"
    sys.modules["core.auth"].create_user = AsyncMock()
    sys.modules["core.auth"].verify_jwt_token = lambda t: {"sub": "1"}
    sys.modules["core.auth"].verify_user_credentials = AsyncMock()
    sys.modules["core.auth"].get_or_create_oidc_user = AsyncMock(
        return_value={
            "id": 1,
            "username": "alice",
            "email": "alice@x.com",
            "role": "user",
        }
    )
    sys.modules["core.oidc"].exchange_code_for_tokens = AsyncMock(
        return_value={"id_token": "idt", "access_token": "act"}
    )
    sys.modules["core.oidc"].verify_id_token = AsyncMock(
        return_value={"sub": "authelia-sub-1"}
    )
    sys.modules["core.oidc"].fetch_userinfo = AsyncMock(return_value={})

    saved_config = sys.modules.get("config")
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        MINDER_OIDC_CLIENT_ID="minder-client",
        MINDER_OIDC_REDIRECT_URI="https://api.minder.local/v1/auth/oidc/callback",
        AUTHELIA_ISSUER_URL="https://authelia.minder.local",
        MINDER_CLIENT_BASE_URL="https://client.minder.local",
        JWT_EXPIRATION_MINUTES=60,
    )
    sys.modules["config"] = cfg

    try:
        spec = importlib.util.spec_from_file_location("oidc_routes_under_test", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


def _set_cookies(response):
    return [v.decode() for k, v in response.raw_headers if k == b"set-cookie"]


# ── oidc_login ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oidc_login_redirects_to_authelia_with_expected_params(auth_route_mod):
    response = await auth_route_mod.oidc_login()

    location = response.headers["location"]
    assert location.startswith("https://authelia.minder.local/api/oidc/authorization?")
    assert "client_id=minder-client" in location
    assert "response_type=code" in location
    assert "scope=openid" in location


@pytest.mark.asyncio
async def test_oidc_login_sets_httponly_state_and_nonce_cookies(auth_route_mod):
    response = await auth_route_mod.oidc_login()

    cookies = _set_cookies(response)
    assert len(cookies) == 2
    assert any(c.startswith("oidc_state=") for c in cookies)
    assert any(c.startswith("oidc_nonce=") for c in cookies)
    assert all("HttpOnly" in c for c in cookies)


# ── oidc_callback ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oidc_callback_provider_error_raises_400(auth_route_mod):
    request = _FakeRequest()

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.oidc_callback(
            request, code=None, state=None, error="access_denied"
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_oidc_callback_state_mismatch_raises_400(auth_route_mod):
    request = _FakeRequest(cookies={"oidc_state": "real-state", "oidc_nonce": "n1"})

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.oidc_callback(
            request, code="authcode", state="wrong-state", error=None
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_oidc_callback_missing_code_raises_400(auth_route_mod):
    request = _FakeRequest(cookies={"oidc_state": "real-state", "oidc_nonce": "n1"})

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.oidc_callback(
            request, code=None, state="real-state", error=None
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_oidc_callback_success_mints_jwt_and_redirects_to_client(
    auth_route_mod,
):
    request = _FakeRequest(cookies={"oidc_state": "s1", "oidc_nonce": "n1"})

    response = await auth_route_mod.oidc_callback(
        request, code="authcode", state="s1", error=None
    )

    location = response.headers["location"]
    assert (
        location == "https://client.minder.local/auth/callback#token=signed.jwt.token"
    )


@pytest.mark.asyncio
async def test_oidc_callback_derives_username_and_email_from_subject_fallback(
    auth_route_mod,
):
    """userinfo and id_token claims both omit preferred_username/email/groups
    (confirmed to happen against a real Authelia instance, per core/oidc.py's
    own docstring) -- the callback must still provision a usable account
    rather than passing None through."""
    request = _FakeRequest(cookies={"oidc_state": "s1", "oidc_nonce": "n1"})

    await auth_route_mod.oidc_callback(request, code="authcode", state="s1", error=None)

    sys.modules["core.auth"].get_or_create_oidc_user.assert_awaited_once_with(
        "authelia-sub-1",
        "authelia-sub-1",
        "authelia-sub-1@authelia.minder.local",
        [],
    )


@pytest.mark.asyncio
async def test_oidc_callback_prefers_userinfo_claims_over_id_token(
    auth_route_mod, monkeypatch
):
    # `from core.oidc import fetch_userinfo` already bound the name directly
    # into auth_route_mod's namespace at import time -- reassigning the
    # attribute on sys.modules["core.oidc"] after the fact wouldn't reach it.
    monkeypatch.setattr(
        auth_route_mod,
        "fetch_userinfo",
        AsyncMock(
            return_value={
                "preferred_username": "alice",
                "email": "alice@example.com",
                "groups": ["admins"],
            }
        ),
    )
    request = _FakeRequest(cookies={"oidc_state": "s1", "oidc_nonce": "n1"})

    await auth_route_mod.oidc_callback(request, code="authcode", state="s1", error=None)

    sys.modules["core.auth"].get_or_create_oidc_user.assert_awaited_once_with(
        "authelia-sub-1", "alice", "alice@example.com", ["admins"]
    )


@pytest.mark.asyncio
async def test_oidc_callback_deletes_state_and_nonce_cookies(auth_route_mod):
    request = _FakeRequest(cookies={"oidc_state": "s1", "oidc_nonce": "n1"})

    response = await auth_route_mod.oidc_callback(
        request, code="authcode", state="s1", error=None
    )

    cookies = _set_cookies(response)
    assert any(c.startswith("oidc_state=") for c in cookies)
    assert any(c.startswith("oidc_nonce=") for c in cookies)
