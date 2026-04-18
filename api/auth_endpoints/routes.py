"""
Authentication endpoints
Handles JWT authentication and user management
"""

import logging

from fastapi import APIRouter, Body, HTTPException, Request

from ..auth import LoginRequest, LoginResponse, get_auth_manager
from ..middleware import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login")
@limiter.limit("10/minute")  # Brute force protection
async def login(request: Request, login_request: LoginRequest = Body(...)):
    """
    Login endpoint - returns JWT access token

    This endpoint can be accessed from trusted networks without authentication
    Rate limited: 10/minute for VPN/public, unlimited for local
    """
    auth_mgr = get_auth_manager()

    # Authenticate user
    user = await auth_mgr.authenticate(login_request.username, login_request.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Generate access token
    access_token = auth_mgr.create_access_token({"sub": user["username"], "role": user["role"]})

    logger.info(f"✅ User logged in: {user['username']} (role: {user['role']})")

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=30 * 60,  # 30 minutes
        user={"username": user["username"], "role": user["role"]},
    )
