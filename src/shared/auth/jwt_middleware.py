"""
JWT Authentication Middleware for Minder Platform
Provides JWT validation and API key authentication for protected endpoints
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)

# Configuration
JWT_SECRET = os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", "60"))

# Security scheme for FastAPI
security = HTTPBearer(auto_error=False)


class JWTAuthMiddleware:
    """JWT Authentication Middleware"""

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or JWT_SECRET
        if not self.secret_key:
            raise ValueError("JWT_SECRET environment variable must be set")

        self.algorithm = JWT_ALGORITHM
        self.expiration_minutes = JWT_EXPIRATION_MINUTES

    def create_token(self, payload: Dict) -> str:
        """Create JWT token with expiration"""
        # Add expiration time
        payload["exp"] = datetime.utcnow() + timedelta(minutes=self.expiration_minutes)
        payload["iat"] = datetime.utcnow()

        token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
        return str(token)

    def decode_token(self, token: str) -> Dict[str, Any]:
        """Decode and validate JWT token"""
        try:
            payload: Dict[str, Any] = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def verify_token(self, credentials: HTTPAuthorizationCredentials) -> Dict:
        """Verify JWT token and return payload"""
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token = credentials.credentials
        payload = self.decode_token(token)
        return payload


# Global JWT auth instance
jwt_auth = JWTAuthMiddleware()


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[Dict]:
    """
    Dependency for protected endpoints
    Returns user payload if authenticated, raises HTTPException if not
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = jwt_auth.verify_token(credentials)
    return payload


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> Optional[Dict]:
    """
    Dependency for endpoints that work with or without authentication
    Returns user payload if authenticated, None if not
    """
    if not credentials:
        return None

    try:
        payload = jwt_auth.verify_token(credentials)
        return payload
    except HTTPException:
        return None


def require_roles(allowed_roles: List[str]):
    """
    Role-based access control decorator
    Usage:
        @require_roles(["admin", "operator"])
        async def protected_endpoint():
            ...
    """

    def decorator(func):
        async def wrapper(*args, current_user: Optional[Dict[str, Any]] = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
                )

            user_role = current_user.get("role", "user")
            if user_role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required roles: {allowed_roles}",
                )

            return await func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator


def create_user_token(
    user_id: str, username: str, role: str = "user", extra_payload: Optional[Dict[str, Any]] = None
) -> str:
    """
    Create JWT token for user

    Args:
        user_id: Unique user identifier
        username: Username
        role: User role (user, admin, operator)
        extra_payload: Additional data to include in token

    Returns:
        JWT token string
    """
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
    }

    if extra_payload:
        payload.update(extra_payload)

    token = jwt_auth.create_token(payload)
    return token


# Rate limiting storage (in production, use Redis)
rate_limit_store: Dict[str, List[datetime]] = {}


async def check_rate_limit(user_id: str, max_requests: int = 60, window_minutes: int = 1) -> bool:
    """
    Check if user has exceeded rate limit

    Args:
        user_id: User identifier
        max_requests: Maximum requests allowed in time window
        window_minutes: Time window in minutes

    Returns:
        True if within limit, False if exceeded
    """
    from datetime import datetime, timedelta

    now = datetime.utcnow()
    window_start = now - timedelta(minutes=window_minutes)

    # Get user's request history
    user_requests = rate_limit_store.get(user_id, [])

    # Filter out requests outside time window
    user_requests = [req_time for req_time in user_requests if req_time > window_start]

    # Check if limit exceeded
    if len(user_requests) >= max_requests:
        return False

    # Add current request
    user_requests.append(now)
    rate_limit_store[user_id] = user_requests

    return True


def enforce_rate_limit(max_requests: int = 60, window_minutes: int = 1):
    """
    Rate limiting decorator for endpoints
    Usage:
        @enforce_rate_limit(max_requests=10, window_minutes=1)
        async def rate_limited_endpoint():
            ...
    """

    def decorator(func):
        async def wrapper(*args, current_user: Optional[Dict[str, Any]] = None, **kwargs):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
                )

            user_id = current_user.get("sub")
            if not await check_rate_limit(str(user_id), max_requests, window_minutes):
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded: {max_requests} requests per {window_minutes} minute(s)",
                )

            return await func(*args, current_user=current_user, **kwargs)

        return wrapper

    return decorator
