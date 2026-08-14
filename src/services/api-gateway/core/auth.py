"""
Authentication Module

Handles JWT token creation, verification, and user authentication.
Real PostgreSQL + bcrypt implementation.
"""

import logging
import pathlib
import secrets
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
            host=settings.DB_HOST,
            port=int(settings.DB_PORT),
            user=settings.DB_USER,
            password=settings.DB_PASSWORD,
            database=settings.DB_NAME,
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


async def create_user(username: str, email: str, password: str) -> Dict[str, Any]:
    """
    Create a new locally-registered user with hashed password. Always role="user"
    (#474) -- there is no caller-controlled way into this function to create an
    admin account. Admin is only ever granted via Authelia OIDC group membership
    (get_or_create_oidc_user), never via /v1/auth/register.

    Args:
        username: Unique username
        email: User email
        password: Plain text password (will be hashed)

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
                VALUES ($1, $2, $3, 'user')
                RETURNING id, username, email, role, is_active, created_at
                """,
                username,
                email,
                password_hash,
            )

            logger.info(f"Created user: {username}")
            return dict(user)

    except asyncpg.UniqueViolationError as e:
        # A duplicate username/email is a conflict, not a bad request (#146).
        if "username" in str(e):
            raise HTTPException(status_code=409, detail="Username already exists")
        elif "email" in str(e):
            raise HTTPException(status_code=409, detail="Email already exists")
        raise HTTPException(status_code=409, detail="User already exists")


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


async def get_or_create_oidc_user(
    authelia_subject: str,
    username: str,
    email: str,
    groups: list,
) -> Dict[str, Any]:
    """Look up (or first-time provision) the Minder user for an Authelia OIDC
    login (#<issue>). Three cases, checked in order:

    1. A user already linked to this authelia_subject -- the common case for
       every login after the first.
    2. A pre-existing local account (created via /v1/auth/register, never
       logged in via SSO before) whose username matches Authelia's
       preferred_username -- link it rather than creating a second,
       disconnected account that would split that person's data (installs,
       etc.) across two ids.
    3. Neither exists -- provision a new row. password_hash still gets a real
       bcrypt hash (the column is NOT NULL) of random bytes nobody knows, so
       /v1/auth/login's own password check simply fails for this account as
       it should -- OIDC users authenticate through Authelia, not locally.

    role is derived from Authelia's groups claim (admins -> "admin", else
    "user") since role predates any code that actually reads it for
    authorization -- see the docs note about RBAC being a tracked follow-up.
    """
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, username, email, role FROM users WHERE authelia_subject = $1",
            authelia_subject,
        )
        if row:
            role = "admin" if "admins" in groups else "user"
            if (
                row["username"] == username
                and row["email"] == email
                and row["role"] == role
            ):
                return dict(row)
            # Keep the local record in sync with Authelia's profile (e.g. a
            # /userinfo call starting to return preferred_username where it
            # didn't before -- exactly what happened during development:
            # the id_token alone gave an opaque UUID subject with no
            # preferred_username at all). Username collisions with an
            # unrelated account are rare enough here to just keep the old
            # value rather than fail the login over a cosmetic sync.
            try:
                updated = await conn.fetchrow(
                    """
                    UPDATE users SET username = $1, email = $2, role = $3, updated_at = NOW()
                    WHERE id = $4
                    RETURNING id, username, email, role
                    """,
                    username,
                    email,
                    role,
                    row["id"],
                )
                return dict(updated)
            except asyncpg.UniqueViolationError:
                logger.warning(
                    f"Could not sync OIDC profile for user {row['id']}: "
                    f"username/email collision with another account"
                )
                return dict(row)

        existing = await conn.fetchrow(
            """
            SELECT id, username, email, role FROM users
            WHERE username = $1 AND authelia_subject IS NULL
            """,
            username,
        )
        if existing:
            role = "admin" if "admins" in groups else "user"
            row = await conn.fetchrow(
                """
                UPDATE users SET authelia_subject = $1, role = $2, updated_at = NOW()
                WHERE id = $3
                RETURNING id, username, email, role
                """,
                authelia_subject,
                role,
                existing["id"],
            )
            logger.info(f"Linked existing local account to Authelia SSO: {username}")
            return dict(row)

        role = "admin" if "admins" in groups else "user"
        placeholder_hash = hashpw(secrets.token_bytes(32), gensalt()).decode("utf-8")
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO users (username, email, password_hash, role, authelia_subject)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, username, email, role
                """,
                username,
                email,
                placeholder_hash,
                role,
                authelia_subject,
            )
        except asyncpg.UniqueViolationError:
            # username or email collided with an unrelated local account
            # (authelia_subject already ruled out above) -- disambiguate by
            # suffixing rather than failing the whole login.
            suffixed = f"{username}-{authelia_subject[:8]}"
            row = await conn.fetchrow(
                """
                INSERT INTO users (username, email, password_hash, role, authelia_subject)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, username, email, role
                """,
                suffixed,
                f"{authelia_subject}@authelia.minder.local",
                placeholder_hash,
                role,
                authelia_subject,
            )
        logger.info(f"Provisioned new user from Authelia SSO: {row['username']}")
        return dict(row)


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
