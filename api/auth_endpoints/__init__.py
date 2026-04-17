"""
Authentication module
Exports authentication components for use in other modules
"""

from ..auth import (
    AuthManager,
    LoginRequest,
    LoginResponse,
    get_auth_manager,
    get_current_user,
    get_current_user_optional,
)

__all__ = [
    "AuthManager",
    "get_auth_manager",
    "get_current_user",
    "get_current_user_optional",
    "LoginRequest",
    "LoginResponse",
]
