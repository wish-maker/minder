"""
Error handling package for Minder.
"""

from .errors import (
    MinderError,
    AuthenticationError,
    AuthorizationError,
    ResourceNotFoundError,
    InputValidationError,
    RateLimitExceededError,
    DatabaseError,
    ExternalServiceError,
    ConflictError,
    ServiceUnavailableError,
    TimeoutError,
)
from .error_handler import ErrorHandler, error_handler, create_error_handler_middleware

__all__ = [
    "MinderError",
    "AuthenticationError",
    "AuthorizationError",
    "ResourceNotFoundError",
    "InputValidationError",
    "RateLimitExceededError",
    "DatabaseError",
    "ExternalServiceError",
    "ConflictError",
    "ServiceUnavailableError",
    "TimeoutError",
    "ErrorHandler",
    "error_handler",
    "create_error_handler_middleware",
]
