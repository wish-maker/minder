"""Authentication endpoints (register / login / refresh).

A plain APIRouter (like routes/ai.py) — all dependencies are module-level imports
(core.auth + config), so no state injection is needed. Auth-table init and pool
teardown stay in main's lifespan.
"""

import logging
import secrets
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlencode

from core.auth import (
    create_jwt_token,
    create_user,
    get_or_create_oidc_user,
    verify_jwt_token,
    verify_user_credentials,
)
from core.oidc import exchange_code_for_tokens, fetch_userinfo, verify_id_token
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from config import settings
from shared.auth.jwt_middleware import enforce_rate_limit

logger = logging.getLogger("minder.api-gateway")

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


# ── Request/response models (#146) ────────────────────────────────────────────
# Previously these endpoints parsed request.json() by hand — /docs showed an empty
# body and missing fields returned an ad-hoc 400. Typed models give FastAPI's automatic
# 422 + full schemas, and one consistent response envelope across the flow.
class RegisterRequest(BaseModel):
    username: str = Field(min_length=1)
    email: str = Field(min_length=1)
    password: str = Field(min_length=8)
    role: str = "user"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    id: int
    username: str
    email: str
    role: str
    created_at: Optional[str] = None


class RegisterResponse(BaseModel):
    message: str = "User created successfully"
    user: UserOut


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Optional[UserOut] = None


@router.post("/register", status_code=201, response_model=RegisterResponse)
@enforce_rate_limit(max_requests=10, window_minutes=1)
async def register(body: RegisterRequest, request: Request):
    """Register a new user (username/email/password, min 8 chars). 201 on success."""
    try:
        user = await create_user(body.username, body.email, body.password, body.role)
        return RegisterResponse(
            user=UserOut(
                id=user["id"],
                username=user["username"],
                email=user["email"],
                role=user["role"],
                created_at=(
                    user["created_at"].isoformat() if user["created_at"] else None
                ),
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login", response_model=TokenResponse)
@enforce_rate_limit(max_requests=10, window_minutes=1)
async def login(body: LoginRequest, request: Request):
    """Verify credentials (bcrypt) against PostgreSQL and return a JWT."""
    try:
        user = await verify_user_credentials(body.username, body.password)
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid username or password")

        access_token = create_jwt_token(
            {
                "sub": str(user["id"]),
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "iat": datetime.now(timezone.utc),
            }
        )
        logger.info(f"User logged in: {body.username}")
        return TokenResponse(
            access_token=access_token,
            expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
            user=UserOut(
                id=user["id"],
                username=user["username"],
                email=user["email"],
                role=user["role"],
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.get("/oidc/login")
async def oidc_login():
    """Start the Authelia SSO redirect -- the platform's single login entry
    point (#<issue>). state/nonce are round-tripped through short-lived
    httponly cookies rather than server-side session storage: this is pure
    CSRF/replay defense for one redirect, not a session (the actual session
    is the Minder JWT oidc_callback mints below, same as local login)."""
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.MINDER_OIDC_CLIENT_ID,
        "redirect_uri": settings.MINDER_OIDC_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email groups",
        "state": state,
        "nonce": nonce,
    }
    url = f"{settings.AUTHELIA_ISSUER_URL}/api/oidc/authorization?{urlencode(params)}"
    response = RedirectResponse(url)
    response.set_cookie(
        "oidc_state", state, max_age=300, httponly=True, secure=True, samesite="lax"
    )
    response.set_cookie(
        "oidc_nonce", nonce, max_age=300, httponly=True, secure=True, samesite="lax"
    )
    return response


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Finish the Authelia SSO redirect: verify the round-tripped state,
    exchange the code for an ID token, verify it, provision/link the Minder
    user, then hand the browser off to the client with a Minder JWT -- same
    shape /v1/auth/login issues, so no downstream service needs to change."""
    if error:
        raise HTTPException(status_code=400, detail=f"OIDC error: {error}")
    cookie_state = request.cookies.get("oidc_state")
    cookie_nonce = request.cookies.get("oidc_nonce")
    if not code or not state or not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")

    tokens = await exchange_code_for_tokens(code)
    claims = await verify_id_token(
        tokens["id_token"], tokens["access_token"], expected_nonce=cookie_nonce or ""
    )
    userinfo = await fetch_userinfo(tokens["access_token"])

    subject = claims["sub"]
    username = (
        userinfo.get("preferred_username")
        or claims.get("preferred_username")
        or subject
    )
    email = (
        userinfo.get("email")
        or claims.get("email")
        or f"{subject}@authelia.minder.local"
    )
    groups = userinfo.get("groups") or claims.get("groups") or []

    user = await get_or_create_oidc_user(subject, username, email, groups)
    access_token = create_jwt_token(
        {
            "sub": str(user["id"]),
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "iat": datetime.now(timezone.utc),
        }
    )
    logger.info(f"User logged in via Authelia SSO: {user['username']}")

    # Fragment, not a query param: browsers never send the URL fragment back
    # to any server (it's client-side-only), so the token never lands in
    # Traefik/api-gateway access logs or Authelia's own redirect history --
    # the client's /auth/callback route reads it from window.location.hash.
    redirect_url = (
        f"{settings.MINDER_CLIENT_BASE_URL}/auth/callback#token={access_token}"
    )
    response = RedirectResponse(redirect_url)
    response.delete_cookie("oidc_state")
    response.delete_cookie("oidc_nonce")
    return response


@router.post("/refresh", response_model=TokenResponse, response_model_exclude_none=True)
async def refresh_token(request: Request):
    """Refresh a JWT from a valid bearer token (sent in the Authorization header)."""
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token required")

    payload = verify_jwt_token(auth_header.split(" ")[1])
    access_token = create_jwt_token(
        {
            "sub": payload.get("sub"),
            "username": payload.get("username"),
            "iat": datetime.now(timezone.utc),
        }
    )
    return TokenResponse(
        access_token=access_token,
        expires_in=settings.JWT_EXPIRATION_MINUTES * 60,
    )
