"""
Shared Pydantic models package
Common request/response models for Minder services
"""

# Import common response models
from .responses import (
    SuccessResponse,
    ErrorResponse,
    PaginatedResponse,
    HealthCheckResponse,
    DetailedHealthCheck,
    CreateResponse,
    UpdateResponse,
    DeleteResponse,
    BatchOperationResponse,
    ValidationErrorResponse,
    ConfigurationResponse,
)

# Import common request models
from .requests import (
    PaginationParams,
    SearchParams,
    FilterParams,
    IdRequest,
    BulkIdsRequest,
    BulkOperationRequest,
    ServiceRequest,
    BatchProcessRequest,
    ExportRequest,
    ImportRequest,
    CacheInvalidationRequest,
    MaintenanceRequest,
    validate_identifier,
    validate_json_field,
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
