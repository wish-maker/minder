"""
Authentication Module

Handles JWT token creation, verification, and user authentication.
Real PostgreSQL + bcrypt implementation.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import asyncpg
from bcrypt import hashpw, checkpw, gensalt
from fastapi import HTTPException, Request
from jose import jwt

from config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# PostgreSQL Connection Pool
# ============================================================================

_pg_pool: Optional[asyncpg.Pool] = None


async def get_pg_pool() -> asyncpg.Pool:
    """Get or create PostgreSQL connection pool"""
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=int(settings.POSTGRES_PORT),
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=1,
            max_size=10,
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
    """Create users table if not exists"""
    pool = await get_pg_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logger.info("Users table ready")


async def create_user(username: str, email: str, password: str, role: str = "user") -> Dict[str, Any]:
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
    password_bytes = password.encode('utf-8')
    password_hash = hashpw(password_bytes, gensalt()).decode('utf-8')

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
                username, email, password_hash, role
            )

            logger.info(f"Created user: {username}")
            return dict(user)

    except asyncpg.UniqueViolationError as e:
        if 'username' in str(e):
            raise HTTPException(status_code=400, detail="Username already exists")
        elif 'email' in str(e):
            raise HTTPException(status_code=400, detail="Email already exists")
        raise HTTPException(status_code=400, detail="User creation failed")


async def verify_user_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
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
            username
        )

        if row is None:
            return None

        user = dict(row)

        # Check if user is active
        if not user['is_active']:
            raise HTTPException(status_code=403, detail="User account is disabled")

        # Verify password with bcrypt
        password_bytes = password.encode('utf-8')
        hash_bytes = user['password_hash'].encode('utf-8')

        if checkpw(password_bytes, hash_bytes):
            # Remove password hash before returning
            del user['password_hash']
            logger.info(f"User authenticated: {username}")
            return user

        return None


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