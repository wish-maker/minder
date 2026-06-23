"""
Shared Pydantic models package
Common request/response models for Minder services
"""

# Import common request models
from .requests import (
    BatchProcessRequest,
    BulkIdsRequest,
    BulkOperationRequest,
    CacheInvalidationRequest,
    ExportRequest,
    FilterParams,
    IdRequest,
    ImportRequest,
    MaintenanceRequest,
    PaginationParams,
    SearchParams,
    ServiceRequest,
    validate_identifier,
    validate_json_field,
)

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
    # Request models
    "PaginationParams",
    "SearchParams",
    "FilterParams",
    "IdRequest",
    "BulkIdsRequest",
    "BulkOperationRequest",
    "ServiceRequest",
    "BatchProcessRequest",
    "ExportRequest",
    "ImportRequest",
    "CacheInvalidationRequest",
    "MaintenanceRequest",
    # Validation helpers
    "validate_identifier",
    "validate_json_field",
]
