"""
Authentication Module

Handles JWT token creation, verification, and user authentication.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import HTTPException, Request
from jose import jwt

from config import settings

logger = logging.getLogger(__name__)


def create_jwt_token(data: Dict[str, Any]) -> str:
    """
    Create JWT access token with expiration

    Args:
        data: Dictionary containing token payload (sub, username, role, etc.)

    Returns:
        Encoded JWT token as string

    Example:
        >>> token = create_jwt_token({"sub": "user123", "username": "admin"})
        >>> len(token) > 100
        True
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def verify_jwt_token(token: str) -> Dict:
    """
    Verify and decode JWT token

    Args:
        token: JWT token to verify

    Returns:
        Decoded token payload

    Raises:
        HTTPException: If token is expired or invalid
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def get_current_user(request: Request):
    """
    Get current user from JWT token (if present)

    Args:
        request: FastAPI request object

    Returns:
        User payload if token present, None otherwise
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ")[1]
    payload = verify_jwt_token(token)
    return payload