"""
JWT Middleware - Shared authentication for microservices

Validates JWT tokens issued by api-gateway.
All services must use the same JWT_SECRET environment variable.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Dict, Optional

from fastapi import HTTPException, Request
from jose import jwt

# ============================================================================
# Configuration
# ============================================================================

# JWT_SECRET is required — fail-fast if not set
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET must be set via environment variable")

JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRATION_MINUTES = int(os.environ.get("JWT_EXPIRATION_MINUTES", "60"))

# Shared secret for trusted internal service-to-service calls (e.g. plugin-registry
# -> marketplace tool sync, which runs at startup with no user JWT). Accepted via the
# X-Service-Token header on the endpoints that opt in (get_current_user_or_service).
# Unset -> service-token auth is disabled and only user JWTs are accepted.
SERVICE_SYNC_TOKEN = os.environ.get("SERVICE_SYNC_TOKEN")


# ============================================================================
# JWT Token Operations
# ============================================================================


def create_jwt_token(data: Dict) -> str:
    """
    Create JWT access token with expiration

    Args:
        data: Dictionary containing token payload (sub, username, role, etc.)

    Returns:
        Encoded JWT token as string
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


# ============================================================================
# FastAPI Dependencies
# ============================================================================


async def get_current_user(request: Request) -> Dict:
    """
    Get current user from JWT token in Authorization header

    This is a dependency for protected endpoints.
    Raises 401 if no valid token present.

    Args:
        request: FastAPI request object

    Returns:
        User payload with keys: sub, username, role

    Raises:
        HTTPException 401: If no token or invalid token
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: 'Bearer <token>'",
        )

    token = auth_header.split(" ")[1]
    payload = verify_jwt_token(token)
    return payload


async def get_current_user_optional(request: Request) -> Optional[Dict]:
    """
    Get current user from JWT token if present (optional)

    Returns None instead of raising 401.
    Use for endpoints that work without auth but have enhanced features with auth.

    Args:
        request: FastAPI request object

    Returns:
        User payload if token valid, None otherwise
    """
    try:
        return await get_current_user(request)
    except HTTPException:
        return None


async def get_current_user_or_service(request: Request) -> Dict:
    """Accept either a valid user JWT OR a trusted internal service token.

    Used by internal service-to-service endpoints (e.g. plugin-registry -> marketplace
    tool sync, which runs at startup with no user context). If the ``X-Service-Token``
    header matches ``SERVICE_SYNC_TOKEN`` (constant-time compare) a service principal is
    returned; otherwise this falls back to ``get_current_user`` (user JWT, 401 if
    invalid). The service token is never accepted when ``SERVICE_SYNC_TOKEN`` is unset.
    """
    svc = request.headers.get("X-Service-Token")
    if SERVICE_SYNC_TOKEN and svc and secrets.compare_digest(svc, SERVICE_SYNC_TOKEN):
        return {
            "sub": "internal-service",
            "username": "service-sync",
            "role": "service",
        }
    return await get_current_user(request)


# ============================================================================
# Rate Limiting
# ============================================================================

# Simple in-memory rate limit store (for single-instance deployments)
# For multi-instance, use Redis instead
_rate_limit_store: Dict[str, list] = {}
_rate_limit_window_seconds = 60


def _prune_rate_limit_key(
    store: Dict[str, list], key: str, window_start: float
) -> None:
    """Drop timestamps older than ``window_start`` for ``key``.

    Removes the key entirely when it empties, so idle user/IP × path combinations
    don't accumulate a permanent (empty-list) entry — keeping the in-memory store
    bounded on a long-lived process.
    """
    if key not in store:
        return
    fresh = [ts for ts in store[key] if ts > window_start]
    if fresh:
        store[key] = fresh
    else:
        del store[key]


def enforce_rate_limit(max_requests: int = 10, window_minutes: int = 1):
    """
    Rate limiting decorator - uses in-memory store

    For production with multiple instances, replace with Redis-based implementation.

    Args:
        max_requests: Maximum requests allowed in window
        window_minutes: Time window in minutes
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Try to get request from kwargs (FastAPI dependency injection)
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break

            if not request:
                # No request object, skip rate limiting
                return await func(*args, **kwargs)

            # Get user identifier
            current_user = getattr(request.state, "user", None)
            if current_user:
                user_id = current_user.get("username", "anonymous")
            else:
                # Fallback to IP address
                user_id = request.client.host if request.client else "anonymous"

            # Check rate limit
            key = f"{user_id}:{request.url.path}"
            now = datetime.now(timezone.utc).timestamp()

            # Clean old entries (and drop the key entirely if it empties)
            window_start = now - (window_minutes * 60)
            _prune_rate_limit_key(_rate_limit_store, key, window_start)

            # Check limit
            if len(_rate_limit_store.get(key, [])) >= max_requests:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded: {max_requests} requests per {window_minutes} minute(s)",
                )

            # Record this request
            if key not in _rate_limit_store:
                _rate_limit_store[key] = []
            _rate_limit_store[key].append(now)

            return await func(*args, **kwargs)

        return wrapper

    return decorator
