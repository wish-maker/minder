"""
Common Pydantic models for standard API responses
Provides consistent response structures across all Minder services
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, TypeVar, Generic
from pydantic import BaseModel, Field


# ============================================================================
# Generic Type Variables
# ============================================================================

T = TypeVar("T")


# ============================================================================
# Standard Response Models
# ============================================================================

class SuccessResponse(BaseModel, Generic[T]):
    """
    Standard success response wrapper

    Example:
        >>> SuccessResponse[data=str](
        ...     success=True,
        ...     message="Operation completed",
        ...     data={"id": 123}
        ... )
    """

    success: bool = True
    message: str = "Operation completed successfully"
    data: Optional[T] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class ErrorResponse(BaseModel):
    """
    Standard error response wrapper

    Example:
        >>> ErrorResponse(
        ...     success=False,
        ...     error="Validation failed",
        ...     detail={"field": "Invalid value"}
        ... )
    """

    success: bool = False
    error: str
    detail: Optional[Any] = None
    timestamp: datetime = Field(default_factory=datetime.now)


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard paginated response

    Example:
        >>> PaginatedResponse[data=str](
        ...     items=[...],
        ...     total=100,
        ...     page=1,
        ...     page_size=10
        ... )
    """

    items: List[T]
    total: int
    page: int = 1
    page_size: int = 10
    total_pages: int = 1
    success: bool = True

    @classmethod
    def create(cls, items: List[T], total: int, page: int = 1, page_size: int = 10):
        """
        Factory method to create paginated response

        Args:
            items: List of items for current page
            total: Total number of items
            page: Current page number (1-indexed)
            page_size: Number of items per page

        Returns:
            PaginatedResponse instance
        """
        total_pages = (total + page_size - 1) // page_size if total > 0 else 1

        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


# ============================================================================
# Health Check Models
# ============================================================================

class HealthCheckResponse(BaseModel):
    """
    Standard health check response

    Example:
        >>> HealthCheckResponse(
        ...     service="marketplace",
        ...     status="healthy",
        ...     version="1.0.0"
        ... )
    """

    service: str
    status: str = Field(..., pattern="^(healthy|unhealthy|degraded)$")
    version: str
    environment: str = "development"
    timestamp: datetime = Field(default_factory=datetime.now)
    checks: Optional[Dict[str, Any]] = None


class ServiceDependency(BaseModel):
    """Service dependency health status"""

    name: str
    status: str
    url: Optional[str] = None
    response_time_ms: Optional[float] = None


class DetailedHealthCheck(BaseModel):
    """
    Detailed health check with dependency status

    Example:
        >>> DetailedHealthCheck(
        ...     service="marketplace",
        ...     status="healthy",
        ...     dependencies=[...]
        ... )
    """

    service: str
    status: str = Field(..., pattern="^(healthy|unhealthy|degraded)$")
    version: str
    dependencies: List[ServiceDependency] = []
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Common CRUD Models
# ============================================================================

class CreateResponse(BaseModel):
    """Response after creating a resource"""

    id: str
    created_at: datetime = Field(default_factory=datetime.now)
    success: bool = True
    message: str = "Resource created successfully"


class UpdateResponse(BaseModel):
    """Response after updating a resource"""

    id: str
    updated_at: datetime = Field(default_factory=datetime.now)
    success: bool = True
    message: str = "Resource updated successfully"
    changes: Optional[Dict[str, Any]] = None


class DeleteResponse(BaseModel):
    """Response after deleting a resource"""

    id: str
    deleted_at: datetime = Field(default_factory=datetime.now)
    success: bool = True
    message: str = "Resource deleted successfully"


# ============================================================================
# Batch Operations
# ============================================================================

class BatchOperationResponse(BaseModel):
    """
    Response for batch operations

    Example:
        >>> BatchOperationResponse(
        ...     operation="batch_create",
        ...     total=10,
        ...     successful=8,
        ...     failed=2
        ... )
    """

    operation: str
    total: int
    successful: int
    failed: int
    errors: Optional[List[Dict[str, Any]]] = None
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Validation Models
# ============================================================================

class ValidationErrorDetail(BaseModel):
    """Detail about a validation error"""

    field: str
    message: str
    value: Optional[Any] = None


class ValidationErrorResponse(BaseModel):
    """Response for validation errors"""

    success: bool = False
    error: str = "Validation failed"
    validation_errors: List[ValidationErrorDetail]
    timestamp: datetime = Field(default_factory=datetime.now)


# ============================================================================
# Configuration
# ============================================================================

class ConfigurationResponse(BaseModel):
    """Response exposing service configuration (safe fields only)"""

    service: str
    version: str
    environment: str
    features: Dict[str, bool] = Field(default_factory=dict)
    limits: Dict[str, int] = Field(default_factory=dict)
    endpoints: Dict[str, str] = Field(default_factory=dict)
