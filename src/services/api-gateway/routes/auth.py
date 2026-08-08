"""Authentication endpoints (register / login / refresh).

A plain APIRouter (like routes/ai.py) — all dependencies are module-level imports
(core.auth + config), so no state injection is needed. Auth-table init and pool
teardown stay in main's lifespan.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from core.auth import (
    create_jwt_token,
    create_user,
    verify_jwt_token,
    verify_user_credentials,
)
from fastapi import APIRouter, HTTPException, Request
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
