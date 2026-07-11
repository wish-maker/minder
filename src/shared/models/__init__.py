"""
Shared Pydantic models package
Common request/response models for Minder services
"""

# Import common response models
from .responses import (
    BatchOperationResponse,
    ConfigurationResponse,
    CreateResponse,
    DeleteResponse,
    DetailedHealthCheck,
    ErrorResponse,
    HealthCheckResponse,
    PaginatedResponse,
    SuccessResponse,
    UpdateResponse,
    ValidationErrorResponse,
)

__all__ = [
    # Response models
    "SuccessResponse",
    "ErrorResponse",
    "PaginatedResponse",
    "HealthCheckResponse",
    "DetailedHealthCheck",
    "CreateResponse",
    "UpdateResponse",
    "DeleteResponse",
    "BatchOperationResponse",
    "ValidationErrorResponse",
    "ConfigurationResponse",
]
