"""
Custom error classes for Minder.
Defines all custom exceptions and error types.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("minder.errors")


class MinderError(Exception):
    """Base error class for Minder"""

    def __init__(
        self,
        message: str,
        code: str = "MINDER_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary"""
        return {
            "message": self.message,
            "code": self.code,
            "status_code": self.status_code,
            "details": self.details,
        }


class AuthenticationError(MinderError):
    """Authentication failed"""

    def __init__(self, message: str = "Authentication failed", details: Optional[Dict] = None):
        super().__init__(message=message, code="AUTH_FAILED", status_code=401, details=details)


class AuthorizationError(MinderError):
    """Authorization failed"""

    def __init__(self, message: str = "Permission denied", details: Optional[Dict] = None):
        super().__init__(
            message=message, code="PERMISSION_DENIED", status_code=403, details=details
        )


class ResourceNotFoundError(MinderError):
    """Resource not found"""

    def __init__(self, resource_type: str, resource_id: str, details: Optional[Dict] = None):
        super().__init__(
            message=f"{resource_type} not found: {resource_id}",
            code="RESOURCE_NOT_FOUND",
            status_code=404,
            details=details,
        )


class InputValidationError(MinderError):
    """Input validation failed"""

    def __init__(self, message: str, field: Optional[str] = None, details: Optional[Dict] = None):
        if details is None:
            details = {}
        if field:
            details["field"] = field
        super().__init__(message=message, code="VALIDATION_ERROR", status_code=422, details=details)


class RateLimitExceededError(MinderError):
    """Rate limit exceeded"""

    def __init__(self, limit: int, window: int, reset_time: int, details: Optional[Dict] = None):
        if details is None:
            details = {}
        details.update({"limit": limit, "window": window, "reset_time": reset_time})
        super().__init__(
            message=f"Rate limit exceeded: {limit} requests per {window} seconds",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details,
        )


class DatabaseError(MinderError):
    """Database operation failed"""

    def __init__(
        self,
        message: str = "Database operation failed",
        operation: Optional[str] = None,
        details: Optional[Dict] = None,
    ):
        if details is None:
            details = {}
        if operation:
            details["operation"] = operation
        super().__init__(message=message, code="DATABASE_ERROR", status_code=500, details=details)


class ExternalServiceError(MinderError):
    """External service call failed"""

    def __init__(
        self,
        service_name: str,
        message: str = "External service error",
        status_code: int = 502,
        details: Optional[Dict] = None,
    ):
        if details is None:
            details = {}
        details["service"] = service_name
        super().__init__(message=message, code="EXTERNAL_SERVICE_ERROR", status_code=status_code, details=details)


class ConflictError(MinderError):
    """Resource conflict"""

    def __init__(self, message: str = "Resource conflict", details: Optional[Dict] = None):
        super().__init__(message=message, code="CONFLICT", status_code=409, details=details)


class ServiceUnavailableError(MinderError):
    """Service temporarily unavailable"""

    def __init__(self, message: str = "Service temporarily unavailable", details: Optional[Dict] = None):
        super().__init__(
            message=message, code="SERVICE_UNAVAILABLE", status_code=503, details=details
        )


class TimeoutError(MinderError):
    """Operation timed out"""

    def __init__(self, operation: str = "Operation", timeout: float = 30.0, details: Optional[Dict] = None):
        if details is None:
            details = {}
        details["operation"] = operation
        details["timeout"] = timeout
        super().__init__(
            message=f"{operation} timed out after {timeout}s",
            code="TIMEOUT",
            status_code=504,
            details=details,
        )
