"""
Authentication module
Exports authentication components for use in other modules
"""

from ..auth import (
    AuthManager,
    get_auth_manager,
    get_current_user,
    get_current_user_optional,
    LoginRequest,
    LoginResponse,
)

__all__ = [
    "AuthManager",
    "get_auth_manager",
    "get_current_user",
    "get_current_user_optional",
    "LoginRequest",
    "LoginResponse",
]
