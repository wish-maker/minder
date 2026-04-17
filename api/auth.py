"""
Authentication & Authorization Module
JWT-based authentication with role-based access control
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
import jwt
from datetime import datetime, timedelta, timezone
import bcrypt
import os
import re
from contextvars import ContextVar
import logging

from .security import InputSanitizer

# Password strength validation
PASSWORD_MIN_LENGTH = 12
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGIT = True
PASSWORD_REQUIRE_SPECIAL = True
SPECIAL_CHARS = '!@#$%^&*(),.?":{}|<>'


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets production security requirements

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < PASSWORD_MIN_LENGTH:
        return False, f"Password must be at least {PASSWORD_MIN_LENGTH} characters"

    if PASSWORD_REQUIRE_UPPERCASE and not re.search(r"[A-Z]", password):
        return False, "Password must contain uppercase letters"

    if PASSWORD_REQUIRE_LOWERCASE and not re.search(r"[a-z]", password):
        return False, "Password must contain lowercase letters"

    if PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        return False, "Password must contain numbers"

    if PASSWORD_REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return False, "Password must contain special characters"

    # Check for common passwords
    common_passwords = ["password", "123456", "qwerty", "admin", "letmein"]
    if password.lower() in common_passwords:
        return False, "Password is too common"

    return True, "Password meets requirements"


logger = logging.getLogger(__name__)

# Configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "30"))

# Context variable for current user
current_user_var: ContextVar[Dict[str, Any]] = ContextVar("current_user", default={})

# Security scheme
security = HTTPBearer()


class AuthManager:
    """Authentication manager for JWT tokens and user credentials"""

    def __init__(self, db_pool=None):
        self.db_pool = db_pool
        # In-memory user storage (will be replaced with database)
        self.users = {}

        # Add default admin user if no users exist
        if not self.users:
            self._create_default_admin()

    def _create_default_admin(self):
        """Create default admin user"""
        admin_password = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        self.users["admin"] = {
            "username": "admin",
            "password_hash": admin_password,
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("✅ Default admin user created " "(username: admin, password: admin123)")

    async def authenticate(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        """Verify credentials against database"""
        user = self.users.get(username)

        if not user:
            logger.warning(f"Authentication failed: User not found: {username}")
            return None

        # Verify password
        try:
            if bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
                logger.info(f"✅ User authenticated successfully: {username}")
                return {
                    "username": user["username"],
                    "role": user["role"],
                    "created_at": user["created_at"],
                }
        except Exception as e:
            logger.error(f"Password verification failed: {e}")

        logger.warning(f"Authentication failed: Invalid password for user: {username}")
        return None

    def create_access_token(self, data: Dict[str, Any]) -> str:
        """Generate JWT access token"""
        to_encode = data.copy()

        # Add expiration time (explicit UTC timezone)
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

        # Generate token
        token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        logger.info(f"✅ Access token created for user: {data.get('username')}")
        return token

    async def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify JWT token and return user data.

        Note: This function does not directly use datetime functions.
        JWT expiration validation is handled by the jwt library internally.
        Token expiration times are timezone-aware from create_access_token.
        """
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")

            # Get user from database
            user = self.users.get(username)
            if not user:
                logger.warning(f"Token verification failed: User not found: {username}")
                return None

            logger.info(f"✅ Token verified successfully for user: {username}")
            return {
                "username": user["username"],
                "role": user["role"],
                "exp": payload.get("exp"),
                "iat": payload.get("iat"),
            }
        except jwt.ExpiredSignatureError:
            logger.warning("Token verification failed: Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Token verification failed: Invalid token - {e}")
            return None
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None

    def create_user(self, username: str, password: str, role: str = "user") -> Dict[str, Any]:
        """Create a new user"""
        if username in self.users:
            raise ValueError(f"User already exists: {username}")

        # Hash password
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        user = {
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        self.users[username] = user
        logger.info(f"✅ User created successfully: {username} (role: {role})")
        return user


# Global auth manager instance (will be initialized at startup)
auth_manager: Optional[AuthManager] = None


def get_auth_manager() -> AuthManager:
    """Get global auth manager instance"""
    if auth_manager is None:
        raise HTTPException(status_code=500, detail="Authentication manager not initialized")
    return auth_manager


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    FastAPI dependency for protected routes

    Verifies JWT token and returns current user data.
    Raises HTTPException if token is invalid.
    """
    auth_mgr = get_auth_manager()

    token = credentials.credentials
    if not token:
        logger.warning("Authentication attempt failed: No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await auth_mgr.verify_token(token)
    if not user:
        logger.warning("Authentication attempt failed: Invalid token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Store in context variable for access in other functions
    current_user_var.set(user)
    return user


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[Dict[str, Any]]:
    """
    Optional authentication dependency - returns None if no token provided

    Used for routes that work with or without authentication.
    """
    if not credentials or not credentials.credentials:
        return None

    auth_mgr = get_auth_manager()
    user = await auth_mgr.verify_token(credentials.credentials)
    return user


async def require_role(*required_roles: str):
    """
    Role-based authorization dependency factory

    Usage:
        @app.get("/admin")
        async def admin_endpoint(user: dict = Depends(require_role("admin"))):
            return {"message": "Admin access granted"}
    """

    async def role_checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in required_roles:
            logger.warning(
                f"Authorization failed: User {user['username']} "
                f"with role {user['role']} attempted to access "
                f"role-restricted endpoint (required: {required_roles})"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Insufficient permissions. " f"Required role: {required_roles[0]}"),
            )
        return user

    return role_checker


class LoginRequest(BaseModel):
    """Login request model"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format and sanitize"""
        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        v = InputSanitizer.sanitize_string(v, max_length=50)

        # Validate format
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, " "hyphens, and underscores")

        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password and sanitize (only check for security issues)"""
        # Check for security issues (but don't modify password)
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        # Don't sanitize password (we need exact value for bcrypt)
        # Just check length
        if len(v) > 100:
            raise ValueError("Password too long (max 100 characters)")

        # Validate password strength for production
        is_strong, strength_error = validate_password_strength(v)
        if not is_strong:
            # For production, enforce strong passwords
            if os.getenv("ENVIRONMENT", "development") == "production":
                raise ValueError(strength_error)
            else:
                # In development, just warn
                logger.warning(f"Weak password detected: {strength_error}")

        return v


class LoginResponse(BaseModel):
    """Login response model"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: Dict[str, Any]


class UserCreateRequest(BaseModel):
    """User creation request model"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)
    role: str = Field("user", pattern="^(admin|user|readonly)$")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format and sanitize"""
        # Check for security issues
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        # Sanitize input
        v = InputSanitizer.sanitize_string(v, max_length=50)

        # Validate format
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username can only contain letters, numbers, " "hyphens, and underscores")

        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Validate password"""
        # Check for security issues (but don't modify password)
        is_valid, error_msg = InputSanitizer.validate_input(v, check_sql=False, check_xss=False)
        if not is_valid:
            raise ValueError(error_msg)

        # Don't sanitize password (we need exact value for bcrypt)
        if len(v) > 100:
            raise ValueError("Password too long (max 100 characters)")

        return v
