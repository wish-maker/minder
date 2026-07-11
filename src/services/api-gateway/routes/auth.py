"""Authentication endpoints (register / login / refresh).

A plain APIRouter (like routes/ai.py) — all dependencies are module-level imports
(modules.auth + config), so no state injection is needed. Auth-table init and pool
teardown stay in main's lifespan.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from modules.auth import (
    create_jwt_token,
    create_user,
    verify_jwt_token,
    verify_user_credentials,
)

from config import settings

logger = logging.getLogger("minder.api-gateway")

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


@router.post("/register")
async def register(request: Request):
    """Register a new user (username/email/password, min 8 chars)."""
    try:
        body = await request.json()
        username = body.get("username")
        email = body.get("email")
        password = body.get("password")
        role = body.get("role", "user")

        if not username or not email or not password:
            raise HTTPException(
                status_code=400, detail="Username, email and password required"
            )
        if len(password) < 8:
            raise HTTPException(
                status_code=400, detail="Password must be at least 8 characters"
            )

        user = await create_user(username, email, password, role)
        return {
            "message": "User created successfully",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
                "created_at": (
                    user["created_at"].isoformat() if user["created_at"] else None
                ),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}")
        raise HTTPException(status_code=500, detail="Registration failed")


@router.post("/login")
async def login(request: Request):
    """Verify credentials (bcrypt) against PostgreSQL and return a JWT."""
    try:
        body = await request.json()
        username = body.get("username")
        password = body.get("password")

        if not username or not password:
            raise HTTPException(
                status_code=400, detail="Username and password required"
            )

        user = await verify_user_credentials(username, password)
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
        logger.info(f"User logged in: {username}")
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
            "user": {
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "role": user["role"],
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}")
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/refresh")
async def refresh_token(request: Request):
    """Refresh a JWT from a valid bearer token."""
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
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_in": settings.JWT_EXPIRATION_MINUTES * 60,
    }
