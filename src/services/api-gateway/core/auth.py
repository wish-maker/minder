"""
Authentication Module

Handles JWT token creation, verification, and user authentication.
Real PostgreSQL + bcrypt implementation.
"""

import logging
import pathlib
import sys
from typing import Any, Dict, Optional

import asyncpg
from bcrypt import checkpw, gensalt, hashpw
from fastapi import HTTPException, Request

from config import settings

# Shared JWT implementation is the single source of truth for token creation and
# verification (issue #49). api-gateway copies src/shared to /app/src/shared but does
# not put it on sys.path by default, so add it here and delegate the JWT functions
# below to shared.auth.jwt_middleware instead of maintaining a divergent fork. Token
# payload/secret/algorithm/expiry are identical (same JWT_* env), so issued tokens stay
# byte-compatible with every downstream service that already uses the shared module.
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.auth import jwt_middleware  # noqa: E402
from shared.db.pool import create_pg_pool  # noqa: E402
from shared.db.schema import apply_schema  # noqa: E402

logger = logging.getLogger(__name__)

_SCHEMA_PATH = pathlib.Path(__file__).parent.parent / "schema.sql"


# ============================================================================
# PostgreSQL Connection Pool
# ============================================================================

_pg_pool: Optional[asyncpg.Pool] = None


async def get_pg_pool() -> asyncpg.Pool:
    """Get or create PostgreSQL connection pool"""
    global _pg_pool
    if _pg_pool is None:
        # command_timeout=None preserves the previous behaviour (no per-command
        # timeout); the shared helper defaults to 60 which callers opt into.
        _pg_pool = await create_pg_pool(
            host=settings.POSTGRES_HOST,
            port=int(settings.POSTGRES_PORT),
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=1,
            max_size=10,
            command_timeout=None,
        )
        logger.info("Created PostgreSQL connection pool for auth")
    return _pg_pool


async def close_pg_pool():
    """Close PostgreSQL connection pool"""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("Closed PostgreSQL connection pool")


# ============================================================================
# User Management
# ============================================================================


async def init_users_table():
    """Create the users table if not present (schema in schema.sql — #17)."""
    pool = await get_pg_pool()
    await apply_schema(pool, _SCHEMA_PATH)
    logger.info("Users table ready")


async def create_user(
    username: str, email: str, password: str, role: str = "user"
) -> Dict[str, Any]:
    """
    Create a new user with hashed password

    Args:
        username: Unique username
        email: User email
        password: Plain text password (will be hashed)
        role: User role (default: 'user')

    Returns:
        Created user data

    Raises:
        HTTPException: If username or email already exists
    """
    # Hash password with bcrypt
    password_bytes = password.encode("utf-8")
    password_hash = hashpw(password_bytes, gensalt()).decode("utf-8")

    pool = await get_pg_pool()
    try:
        async with pool.acquire() as conn:
            # Use fetchrow for INSERT ... RETURNING
            user = await conn.fetchrow(
                """
                INSERT INTO users (username, email, password_hash, role)
                VALUES ($1, $2, $3, $4)
                RETURNING id, username, email, role, is_active, created_at
                """,
                username,
                email,
                password_hash,
                role,
            )

            logger.info(f"Created user: {username}")
            return dict(user)

    except asyncpg.UniqueViolationError as e:
        if "username" in str(e):
            raise HTTPException(status_code=400, detail="Username already exists")
        elif "email" in str(e):
            raise HTTPException(status_code=400, detail="Email already exists")
        raise HTTPException(status_code=400, detail="User creation failed")


async def verify_user_credentials(
    username: str, password: str
) -> Optional[Dict[str, Any]]:
    """
    Verify user credentials against database

    Args:
        username: Username to verify
        password: Plain text password

    Returns:
        User data if credentials valid, None otherwise
    """
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        # Use fetchrow to get a single record
        row = await conn.fetchrow(
            """
            SELECT id, username, email, password_hash, role, is_active
            FROM users WHERE username = $1
            """,
            username,
        )

        if row is None:
            return None

        user = dict(row)

        # Check if user is active
        if not user["is_active"]:
            raise HTTPException(status_code=403, detail="User account is disabled")

        # Verify password with bcrypt
        password_bytes = password.encode("utf-8")
        hash_bytes = user["password_hash"].encode("utf-8")

        if checkpw(password_bytes, hash_bytes):
            # Remove password hash before returning
            del user["password_hash"]
            logger.info(f"User authenticated: {username}")
            return user

        return None


def create_jwt_token(data: Dict[str, Any]) -> str:
    """
    Create JWT access token with expiration.

    Thin delegate to ``shared.auth.jwt_middleware.create_jwt_token`` so token issuance
    lives in exactly one place (issue #49). Reads the same JWT_SECRET/JWT_ALGORITHM/
    JWT_EXPIRATION_MINUTES environment variables api-gateway's ``settings`` reads, so the
    emitted tokens are unchanged.

    Args:
        data: Dictionary containing token payload (sub, username, role, etc.)

    Returns:
        Encoded JWT token as string
    """
    return jwt_middleware.create_jwt_token(data)


def verify_jwt_token(token: str) -> Dict:
    """
    Verify and decode a JWT token.

    Thin delegate to ``shared.auth.jwt_middleware.verify_jwt_token`` (issue #49).

    Args:
        token: JWT token to verify

    Returns:
        Decoded token payload

    Raises:
        HTTPException: 401 if the token is expired or invalid
    """
    return jwt_middleware.verify_jwt_token(token)


async def get_current_user(request: Request) -> Optional[Dict]:
    """
    Get current user from the JWT token if present, otherwise None.

    api-gateway historically treats auth as optional at this layer (write protection is
    enforced explicitly in ``routes/proxy.py``), so this preserves the return-None-on-
    missing-token behaviour by delegating to the shared *optional* dependency rather than
    the raising ``get_current_user`` (issue #49).

    Args:
        request: FastAPI request object

    Returns:
        User payload if a valid token is present, None otherwise
    """
    return await jwt_middleware.get_current_user_optional(request)
