"""
Comprehensive error handling for Minder services.
Standardized error responses and logging.
"""

import logging
import traceback
from typing import Any, Dict, Optional

import aiohttp
from asyncpg import PostgresConnectionError, PostgresError
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError as PydanticValidationError

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

logger = logging.getLogger("minder.error_handler")


class ErrorHandler:
    """
    Centralized error handler for Minder services.
    Provides consistent error responses and logging.
    """

    def __init__(self, service_name: str = "minder"):
        """
        Initialize error handler.

        Args:
            service_name: Name of the service
        """
        self.service_name = service_name

    def handle_exception(
        self,
        exception: Exception,
        request: Optional[Request] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ) -> JSONResponse:
        """
        Handle an exception and return standardized response.

        Args:
            exception: Exception to handle
            request: Optional request object
            additional_context: Optional additional context to include

        Returns:
            JSONResponse with error information
        """
        # Log the error
        self._log_exception(exception, request, additional_context)

        # Convert to standard response
        if isinstance(exception, MinderError):
            return self._handle_minder_error(exception, request)
        elif isinstance(exception, HTTPException):
            return self._handle_http_exception(exception, request)
        elif isinstance(exception, PydanticValidationError):
            return self._handle_validation_error(exception, request)
        elif isinstance(exception, PostgresError):
            return self._handle_database_error(exception, request)
        elif isinstance(exception, aiohttp.ClientError):
            return self._handle_external_service_error(exception, request)
        else:
            return self._handle_generic_error(exception, request)

    def _log_exception(
        self,
        exception: Exception,
        request: Optional[Request] = None,
        additional_context: Optional[Dict[str, Any]] = None,
    ):
        """Log the exception with context"""
        context_str = ""

        if request:
            context_str += f" | Request: {request.method} {request.url.path}"

        if additional_context:
            context_str += f" | Context: {additional_context}"

        logger.error(
            f"Error in {self.service_name}: {str(exception)}{context_str}\n"
            f"Traceback:\n{traceback.format_exc()}"
        )

    def _handle_minder_error(
        self, exception: MinderError, request: Optional[Request]
    ) -> JSONResponse:
        """Handle custom Minder errors"""
        response_data = exception.to_dict()

        if request:
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(
            status_code=exception.status_code,
            content=response_data,
        )

    def _handle_http_exception(
        self, exception: HTTPException, request: Optional[Request]
    ) -> JSONResponse:
        """Handle FastAPI HTTP exceptions"""
        response_data = {
            "message": exception.detail,
            "code": f"HTTP_{exception.status_code}",
            "status_code": exception.status_code,
        }

        if request:
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(
            status_code=exception.status_code,
            content=response_data,
        )

    def _handle_validation_error(
        self, exception: PydanticValidationError, request: Optional[Request]
    ) -> JSONResponse:
        """Handle Pydantic validation errors"""
        response_data = {
            "message": "Validation failed",
            "code": "VALIDATION_ERROR",
            "status_code": 422,
            "details": {
                "errors": exception.errors(),
            },
        }

        if request:
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(
            status_code=422,
            content=response_data,
        )

    def _handle_database_error(
        self, exception: PostgresError, request: Optional[Request]
    ) -> JSONResponse:
        """Handle database errors"""
        error_details = {"error": str(exception)}

        if isinstance(exception, PostgresConnectionError):
            response_data = {
                "message": "Database connection error",
                "code": "DATABASE_CONNECTION_ERROR",
                "status_code": 503,
                "details": error_details,
            }
        else:
            response_data = {
                "message": "Database error",
                "code": "DATABASE_ERROR",
                "status_code": 500,
                "details": error_details,
            }

        if request:
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(
            status_code=response_data["status_code"],
            content=response_data,
        )

    def _handle_external_service_error(
        self, exception: aiohttp.ClientError, request: Optional[Request]
    ) -> JSONResponse:
        """Handle external service errors"""
        response_data = {
            "message": "External service error",
            "code": "EXTERNAL_SERVICE_ERROR",
            "status_code": 502,
            "details": {"error": str(exception)},
        }

        if request:
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(
            status_code=502,
            content=response_data,
        )

    def _handle_generic_error(
        self, exception: Exception, request: Optional[Request]
    ) -> JSONResponse:
        """Handle generic exceptions"""
        response_data = {
            "message": "Internal server error",
            "code": "INTERNAL_ERROR",
            "status_code": 500,
            "details": {"error": str(exception)},
        }

        if request:
            response_data["request_id"] = getattr(request.state, "request_id", None)

        return JSONResponse(
            status_code=500,
            content=response_data,
        )


# Global error handler instance
error_handler = ErrorHandler()


def create_error_handler_middleware(service_name: str = "minder"):
    """
    Create error handler middleware for FastAPI.

    Args:
        service_name: Name of the service

    Returns:
        Middleware function
    """
    handler = ErrorHandler(service_name)

    async def error_handler_middleware(request: Request, call_next):
        """Error handler middleware"""
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            return handler.handle_exception(e, request)

    return error_handler_middleware
