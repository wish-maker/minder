"""Unit tests filling routes/auth.py's remaining coverage gaps (77%).

test_oidc_routes.py already covers oidc_login/oidc_callback plus one
register-rate-limit-config test; test_api_gateway_user_credentials.py covers
core.auth's create_user/verify_user_credentials directly. Neither exercises
the route-layer login()/refresh_token() functions at all, nor register()'s
own generic-exception->500 branch -- this file adds all three.

Same core/core.auth/core.oidc/config sys.modules-faking + module-loading
pattern as test_oidc_routes.py's auth_route_mod fixture. register/login are
wrapped in @enforce_rate_limit, which reads request.client.host + request.url
.path from a real Request -- a plain object with a `.headers` dict isn't
enough for those two (refresh_token has no rate limit and only reads
request.headers, so a lighter fake is fine there).
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from starlette.datastructures import Headers
from starlette.types import Scope

from shared.auth.jwt_middleware import _rate_limit_store

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "auth.py"
)


def _http_request(path="/v1/auth/login", client_ip="10.0.0.1", headers=None):
    scope: Scope = {
        "type": "http",
        "path": path,
        "headers": Headers(headers or {}).raw,
        "client": (client_ip, 12345),
    }
    return Request(scope)


class _FakeRequest:
    """refresh_token only ever calls request.headers.get(...) -- no need for
    a real Request (it isn't rate-limited)."""

    def __init__(self, headers=None):
        self.headers = headers or {}


@pytest.fixture
def auth_route_mod():
    names = ("core", "core.auth", "core.oidc")
    saved = {n: sys.modules.get(n) for n in names}
    for n in names:
        sys.modules[n] = ModuleType(n)
    sys.modules["core.auth"].create_jwt_token = lambda data: "signed.jwt.token"
    sys.modules["core.auth"].create_user = AsyncMock()
    sys.modules["core.auth"].verify_jwt_token = lambda t: {
        "sub": "1",
        "username": "alice",
        "email": "alice@x.com",
        "role": "user",
    }
    sys.modules["core.auth"].verify_user_credentials = AsyncMock()
    sys.modules["core.auth"].get_or_create_oidc_user = AsyncMock()
    sys.modules["core.oidc"].exchange_code_for_tokens = AsyncMock()
    sys.modules["core.oidc"].verify_id_token = AsyncMock()
    sys.modules["core.oidc"].fetch_userinfo = AsyncMock()

    saved_config = sys.modules.get("config")
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(
        MINDER_OIDC_CLIENT_ID="minder-client",
        MINDER_OIDC_REDIRECT_URI="https://api.minder.local/v1/auth/oidc/callback",
        AUTHELIA_ISSUER_URL="https://authelia.minder.local",
        MINDER_CLIENT_BASE_URL="https://client.minder.local",
        JWT_EXPIRATION_MINUTES=60,
        # High enough that no test below can trip the rate limiter itself --
        # that behavior already has its own dedicated test in
        # test_oidc_routes.py.
        AUTH_RATE_LIMIT_PER_MINUTE=1000,
    )
    sys.modules["config"] = cfg
    _rate_limit_store.clear()

    try:
        spec = importlib.util.spec_from_file_location(
            "auth_routes_coverage_under_test", _ROUTE
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        _rate_limit_store.clear()
        for n, m in saved.items():
            if m is not None:
                sys.modules[n] = m
            else:
                sys.modules.pop(n, None)
        if saved_config is not None:
            sys.modules["config"] = saved_config
        else:
            sys.modules.pop("config", None)


# ── register: exception handling ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_reraises_http_exception_unchanged(auth_route_mod, monkeypatch):
    # `from core.auth import create_user` already bound the name directly into
    # auth_route_mod's namespace at import time -- reassigning the attribute
    # on sys.modules["core.auth"] after the fact wouldn't reach it (same gotcha
    # test_oidc_routes.py hit for fetch_userinfo).
    monkeypatch.setattr(
        auth_route_mod,
        "create_user",
        AsyncMock(side_effect=HTTPException(status_code=409, detail="username taken")),
    )
    body = auth_route_mod.RegisterRequest(
        username="bob", email="bob@x.com", password="password123"
    )

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.register(body, _http_request("/v1/auth/register"))

    assert exc.value.status_code == 409
    assert exc.value.detail == "username taken"


@pytest.mark.asyncio
async def test_register_masks_unexpected_errors_as_500(auth_route_mod, monkeypatch):
    monkeypatch.setattr(
        auth_route_mod,
        "create_user",
        AsyncMock(side_effect=RuntimeError("db unreachable")),
    )
    body = auth_route_mod.RegisterRequest(
        username="bob", email="bob@x.com", password="password123"
    )

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.register(body, _http_request("/v1/auth/register"))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Registration failed"
    assert (
        "db unreachable" not in exc.value.detail
    )  # raw error never leaks to the client


# ── login ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_invalid_credentials_raises_401(auth_route_mod, monkeypatch):
    monkeypatch.setattr(
        auth_route_mod, "verify_user_credentials", AsyncMock(return_value=None)
    )
    body = auth_route_mod.LoginRequest(username="bob", password="wrong")

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.login(body, _http_request("/v1/auth/login", "10.0.0.2"))

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_success_returns_signed_jwt_and_user(auth_route_mod, monkeypatch):
    monkeypatch.setattr(
        auth_route_mod,
        "verify_user_credentials",
        AsyncMock(
            return_value={
                "id": 1,
                "username": "bob",
                "email": "bob@x.com",
                "role": "user",
            }
        ),
    )
    body = auth_route_mod.LoginRequest(username="bob", password="correct")

    result = await auth_route_mod.login(
        body, _http_request("/v1/auth/login", "10.0.0.3")
    )

    assert result.access_token == "signed.jwt.token"
    assert result.token_type == "bearer"
    assert result.expires_in == 60 * 60
    assert result.user.username == "bob"


@pytest.mark.asyncio
async def test_login_masks_unexpected_errors_as_500(auth_route_mod, monkeypatch):
    monkeypatch.setattr(
        auth_route_mod,
        "verify_user_credentials",
        AsyncMock(side_effect=RuntimeError("pool exhausted")),
    )
    body = auth_route_mod.LoginRequest(username="bob", password="correct")

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.login(body, _http_request("/v1/auth/login", "10.0.0.4"))

    assert exc.value.status_code == 500
    assert exc.value.detail == "Login failed"
    assert "pool exhausted" not in exc.value.detail


# ── refresh_token ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_refresh_token_missing_authorization_header_raises_401(auth_route_mod):
    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.refresh_token(_FakeRequest())

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_non_bearer_header_raises_401(auth_route_mod):
    request = _FakeRequest(headers={"Authorization": "Basic dXNlcjpwYXNz"})

    with pytest.raises(HTTPException) as exc:
        await auth_route_mod.refresh_token(request)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_success_mints_a_new_signed_jwt(
    auth_route_mod, monkeypatch
):
    monkeypatch.setattr(
        auth_route_mod,
        "verify_jwt_token",
        lambda t: {
            "sub": "1",
            "username": "bob",
            "email": "bob@x.com",
            "role": "user",
        },
    )
    request = _FakeRequest(headers={"Authorization": "Bearer old.jwt.token"})

    result = await auth_route_mod.refresh_token(request)

    assert result.access_token == "signed.jwt.token"
    assert result.expires_in == 60 * 60
    assert result.user is None  # refresh never re-attaches the user block
