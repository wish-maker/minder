"""
Comprehensive error handling for Minder services.
Standardized error responses and logging.
"""

import logging
import traceback
from typing import Any, Dict, Optional

import aiohttp
from asyncpg import PostgresConnectionError, PostgresError
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

from .validators import ValidationError

logger = logging.getLogger("minder.error_handler")


# Custom error classes


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


class ValidationError(MinderError):
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


class ServiceUnavailableError(MinderError):
    """Service temporarily unavailable"""

    def __init__(self, service: str, details: Optional[Dict] = None):
        super().__init__(
            message=f"Service unavailable: {service}",
            code="SERVICE_UNAVAILABLE",
            status_code=503,
            details=details,
        )


class DatabaseError(MinderError):
    """Database operation failed"""

    def __init__(self, message: str = "Database operation failed", details: Optional[Dict] = None):
        super().__init__(message=message, code="DATABASE_ERROR", status_code=500, details=details)


class ExternalServiceError(MinderError):
    """External API call failed"""

    def __init__(
        self,
        service: str,
        message: str = "External service call failed",
        details: Optional[Dict] = None,
    ):
        if details is None:
            details = {}
        details["service"] = service
        super().__init__(
            message=message, code="EXTERNAL_SERVICE_ERROR", status_code=502, details=details
        )


# Error response model


class ErrorResponse:
    """Standardized error response"""

    @staticmethod
    def create(
        error_code: str,
        message: str,
        status_code: int,
        details: Optional[Dict[str, Any]] = None,
        request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create standardized error response.

        Args:
            error_code: Application-specific error code
            message: Human-readable error message
            status_code: HTTP status code
            details: Additional error details
            request_id: Request correlation ID

        Returns:
            Dictionary with error information
        """
        response = {"error": {"code": error_code, "message": message, "status_code": status_code}}

        if details:
            response["error"]["details"] = details

        if request_id:
            response["request_id"] = request_id

        return response


# Exception handlers


async def minder_exception_handler(request: Request, exc: MinderError) -> JSONResponse:
    """Handle Minder-specific exceptions"""

    # Get request ID from headers
    request_id = request.headers.get("X-Request-ID")

    # Create error response
    error_data = ErrorResponse.create(
        error_code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        request_id=request_id,
    )

    # Log error
    logger.error(
        f"MinderError: {exc.code} - {exc.message}",
        extra={
            "error_code": exc.code,
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "details": exc.details,
        },
    )

    return JSONResponse(status_code=exc.status_code, content=error_data)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handle FastAPI HTTP exceptions"""

    request_id = request.headers.get("X-Request-ID")

    error_data = ErrorResponse.create(
        error_code=f"HTTP_{exc.status_code}",
        message=exc.detail,
        status_code=exc.status_code,
        request_id=request_id,
    )

    # Log HTTP errors
    logger.warning(
        f"HTTPException: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(status_code=exc.status_code, content=error_data)


async def validation_exception_handler(
    request: Request, exc: PydanticValidationError
) -> JSONResponse:
    """Handle Pydantic validation errors"""

    request_id = request.headers.get("X-Request-ID")

    # Extract field errors
    errors = []
    for error in exc.errors():
        errors.append(
            {
                "field": ".".join(str(loc) for loc in error["loc"]),
                "message": error["msg"],
                "type": error["type"],
            }
        )

    error_data = ErrorResponse.create(
        error_code="VALIDATION_ERROR",
        message="Input validation failed",
        status_code=422,
        details={"fields": errors},
        request_id=request_id,
    )

    # Log validation errors
    logger.warning(
        f"ValidationError: {len(errors)} field(s) failed validation",
        extra={
            "error_code": "VALIDATION_ERROR",
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "validation_errors": errors,
        },
    )

    return JSONResponse(status_code=422, content=error_data)


async def postgres_exception_handler(request: Request, exc: PostgresError) -> JSONResponse:
    """Handle PostgreSQL errors"""

    request_id = request.headers.get("X-Request-ID")

    error_data = ErrorResponse.create(
        error_code="DATABASE_ERROR",
        message="Database operation failed",
        status_code=500,
        details={"detail": str(exc), "hint": getattr(exc, "hint", None)},
        request_id=request_id,
    )

    # Log database errors
    logger.error(
        f"PostgresError: {str(exc)}",
        extra={
            "error_code": "DATABASE_ERROR",
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "postgres_detail": str(exc),
        },
        exc_info=True,
    )

    return JSONResponse(status_code=500, content=error_data)


async def aiohttp_exception_handler(request: Request, exc: aiohttp.ClientError) -> JSONResponse:
    """Handle aiohttp client errors (external service calls)"""

    request_id = request.headers.get("X-Request-ID")

    error_data = ErrorResponse.create(
        error_code="EXTERNAL_SERVICE_ERROR",
        message="External service call failed",
        status_code=502,
        details={"detail": str(exc)},
        request_id=request_id,
    )

    # Log external service errors
    logger.error(
        f"ExternalServiceError: {str(exc)}",
        extra={
            "error_code": "EXTERNAL_SERVICE_ERROR",
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "aiohttp_error": str(exc),
        },
    )

    return JSONResponse(status_code=502, content=error_data)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle all other exceptions"""

    request_id = request.headers.get("X-Request-ID")

    # Get traceback
    tb_str = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    error_data = ErrorResponse.create(
        error_code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred",
        status_code=500,
        request_id=request_id,
    )

    # Log unexpected errors
    logger.error(
        f"UnexpectedError: {type(exc).__name__} - {str(exc)}",
        extra={
            "error_code": "INTERNAL_SERVER_ERROR",
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "traceback": tb_str,
        },
        exc_info=True,
    )

    # Don't include traceback in production response
    return JSONResponse(status_code=500, content=error_data)


# Middleware setup


def setup_error_handlers(app):
    """
    Setup all exception handlers for FastAPI app.

    Args:
        app: FastAPI application instance

    Example:
        from fastapi import FastAPI
        app = FastAPI()
        setup_error_handlers(app)
    """
    # Minder-specific exceptions
    app.add_exception_handler(MinderError, minder_exception_handler)
    app.add_exception_handler(AuthenticationError, minder_exception_handler)
    app.add_exception_handler(AuthorizationError, minder_exception_handler)
    app.add_exception_handler(ResourceNotFoundError, minder_exception_handler)
    app.add_exception_handler(ValidationError, minder_exception_handler)
    app.add_exception_handler(RateLimitExceededError, minder_exception_handler)
    app.add_exception_handler(ServiceUnavailableError, minder_exception_handler)
    app.add_exception_handler(DatabaseError, minder_exception_handler)
    app.add_exception_handler(ExternalServiceError, minder_exception_handler)

    # Framework exceptions
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)

    # Database exceptions
    app.add_exception_handler(PostgresError, postgres_exception_handler)
    app.add_exception_handler(PostgresConnectionError, postgres_exception_handler)

    # External service exceptions
    app.add_exception_handler(aiohttp.ClientError, aiohttp_exception_handler)

    # Generic exception handler (must be last)
    app.add_exception_handler(Exception, generic_exception_handler)

    logger.info("Error handlers registered")


# Error logging decorator


def log_errors(func):
    """
    Decorator to log errors from functions.

    Example:
        @log_errors
        async def my_function():
            pass
    """

    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(
                f"Error in {func.__name__}: {str(e)}",
                extra={
                    "function": func.__name__,
                    "exception_type": type(e).__name__,
                    "args": args,
                    "kwargs": kwargs,
                },
                exc_info=True,
            )
            raise

    return wrapper


# Error context manager


class ErrorHandler:
    """Context manager for handling errors"""

    def __init__(self, operation: str, reraise: bool = False):
        """
        Initialize error handler.

        Args:
            operation: Description of operation being performed
            reraise: Whether to reraise exception after logging
        """
        self.operation = operation
        self.reraise = reraise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            logger.error(
                f"Error in operation '{self.operation}': {str(exc_val)}",
                extra={
                    "operation": self.operation,
                    "exception_type": exc_type.__name__,
                    "exception_value": str(exc_val),
                },
                exc_info=True,
            )
            return not self.reraise
        return False


def safe_execute(operation: str, reraise: bool = False):
    """
    Decorator for safe execution with error handling.

    Args:
        operation: Description of operation
        reraise: Whether to reraise exception

    Example:
        @safe_execute("database operation")
        async def my_function():
            pass
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            with ErrorHandler(operation, reraise):
                return await func(*args, **kwargs)

        return wrapper

    return decorator
