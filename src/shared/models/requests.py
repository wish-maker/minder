"""
Common Pydantic models for standard API requests
Provides consistent request validation across all Minder services
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# ============================================================================
# Pagination
# ============================================================================


class PaginationParams(BaseModel):
    """
    Standard pagination parameters

    Example:
        >>> params = PaginationParams(page=1, page_size=20)
    """

    page: int = Field(1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(10, ge=1, le=100, description="Number of items per page")
    sort_by: Optional[str] = Field(None, description="Field to sort by")
    sort_order: str = Field("asc", pattern="^(asc|desc)$", description="Sort order")

    @property
    def offset(self) -> int:
        """Calculate offset for database queries"""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit for database queries"""
        return self.page_size


# ============================================================================
# Search and Filter
# ============================================================================


class SearchParams(BaseModel):
    """
    Standard search parameters

    Example:
        >>> params = SearchParams(query="ai", filters={"tag": "ml"})
    """

    query: Optional[str] = Field(
        None, min_length=1, max_length=200, description="Search query"
    )
    filters: Dict[str, Any] = Field(default_factory=dict, description="Filter criteria")
    exact_match: bool = Field(
        False, description="Use exact match instead of fuzzy search"
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, v: Optional[str]) -> Optional[str]:
        """Clean and validate search query"""
        if v is not None:
            # Remove excessive whitespace
            v = re.sub(r"\s+", " ", v).strip()
            # Prevent SQL injection patterns (basic check)
            if any(char in v for char in [";--", "/*", "*/", "xp_", "exec("]):
                raise ValueError("Query contains potentially harmful characters")
        return v


class FilterParams(BaseModel):
    """
    Standard filter parameters

    Example:
        >>> params = FilterParams(
        ...     tags=["machine-learning", "nlp"],
        ...     status="active",
        ...     date_from="2024-01-01"
        ... )
    """

    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    status: Optional[str] = Field(None, description="Filter by status")
    date_from: Optional[str] = Field(None, description="Filter from date (ISO format)")
    date_to: Optional[str] = Field(None, description="Filter to date (ISO format)")
    created_by: Optional[str] = Field(None, description="Filter by creator")

    @field_validator("date_from", "date_to")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format"""
        if v is not None:
            try:
                datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError("Invalid date format. Use ISO format: YYYY-MM-DD")
        return v


# ============================================================================
# Common CRUD Operations
# ============================================================================


class IdRequest(BaseModel):
    """Request with single ID"""

    id: str = Field(..., min_length=1, description="Resource identifier")


class BulkIdsRequest(BaseModel):
    """Request with multiple IDs"""

    ids: List[str] = Field(
        ..., min_length=1, description="List of resource identifiers"
    )

    @field_validator("ids")
    @classmethod
    def validate_ids(cls, v: List[str]) -> List[str]:
        """Validate and clean IDs"""
        if len(v) > 100:
            raise ValueError("Cannot process more than 100 IDs at once")
        return [id.strip() for id in v if id.strip()]


class BulkOperationRequest(BaseModel):
    """Request for bulk operations"""

    operation: str = Field(..., pattern="^(delete|update|enable|disable)$")
    ids: List[str] = Field(..., min_length=1, max_length=100)
    parameters: Optional[Dict[str, Any]] = Field(default_factory=dict)


# ============================================================================
# Service Communication
# ============================================================================


class ServiceRequest(BaseModel):
    """
    Request for service-to-service communication

    Example:
        >>> req = ServiceRequest(
        ...     source_service="marketplace",
        ...     target_service="plugin-registry",
        ...     action="register_plugin",
        ...     payload={...}
        ... )
    """

    source_service: str = Field(..., description="Name of the calling service")
    target_service: str = Field(..., description="Name of the target service")
    action: str = Field(..., description="Action to perform")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Request payload")
    request_id: Optional[str] = Field(
        None, description="Unique request identifier for tracing"
    )


# ============================================================================
# Batch Processing
# ============================================================================


class BatchProcessRequest(BaseModel):
    """
    Request for batch processing

    Example:
        >>> req = BatchProcessRequest(
        ...     operation="import",
        ...     items=[...],
        ...     parallel=True,
        ...     batch_size=10
        ... )
    """

    operation: str = Field(..., description="Operation to perform")
    items: List[Dict[str, Any]] = Field(
        ..., min_length=1, max_length=1000, description="Items to process"
    )
    parallel: bool = Field(False, description="Process items in parallel")
    batch_size: int = Field(10, ge=1, le=100, description="Number of items per batch")
    options: Dict[str, Any] = Field(
        default_factory=dict, description="Additional options"
    )


# ============================================================================
# Export/Import
# ============================================================================


class ExportRequest(BaseModel):
    """
    Request for data export

    Example:
        >>> req = ExportRequest(
        ...     format="json",
        ...     filters={"status": "active"},
        ...     include_metadata=True
        ... )
    """

    format: str = Field(
        "json", pattern="^(json|csv|yaml)$", description="Export format"
    )
    filters: Dict[str, Any] = Field(
        default_factory=dict, description="Filters to apply"
    )
    include_metadata: bool = Field(False, description="Include metadata in export")
    compress: bool = Field(False, description="Compress output")


class ImportRequest(BaseModel):
    """
    Request for data import

    Example:
        >>> req = ImportRequest(
        ...     format="json",
        ...     data={...},
        ...     overwrite=False,
        ...     skip_errors=True
        ... )
    """

    format: str = Field(
        "json", pattern="^(json|csv|yaml)$", description="Import format"
    )
    data: Dict[str, Any] = Field(..., description="Data to import")
    overwrite: bool = Field(False, description="Overwrite existing data")
    skip_errors: bool = Field(True, description="Continue on errors")
    validate_only: bool = Field(False, description="Only validate without importing")


# ============================================================================
# Admin Operations
# ============================================================================


class CacheInvalidationRequest(BaseModel):
    """Request to invalidate cache"""

    cache_keys: Optional[List[str]] = Field(
        None, description="Specific cache keys to invalidate"
    )
    pattern: Optional[str] = Field(
        None, description="Pattern for cache keys to invalidate"
    )
    invalidate_all: bool = Field(False, description="Invalidate all cache")


class MaintenanceRequest(BaseModel):
    """Request for maintenance operations"""

    operation: str = Field(..., pattern="^(vacuum|analyze|reindex|cleanup)$")
    tables: Optional[List[str]] = Field(
        None, description="Specific tables to operate on"
    )
    dry_run: bool = Field(False, description="Simulate without executing")


# ============================================================================
# Validation Helpers
# ============================================================================


def validate_identifier(value: str) -> str:
    """
    Validate identifier format (alphanumeric, hyphens, underscores)

    Args:
        value: Identifier to validate

    Returns:
        Validated identifier

    Raises:
        ValueError: If identifier is invalid
    """
    if not re.match(r"^[a-zA-Z0-9_-]+$", value):
        raise ValueError(
            "Identifier must contain only alphanumeric characters, hyphens, and underscores"
        )
    if len(value) > 100:
        raise ValueError("Identifier must not exceed 100 characters")
    return value


def validate_json_field(value: Any) -> Dict[str, Any]:
    """
    Validate JSON field

    Args:
        value: Value to validate as JSON-compatible

    Returns:
        Validated dictionary

    Raises:
        ValueError: If value cannot be serialized to JSON
    """
    if value is None:
        return {}

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            import json

            return json.loads(value)
        except json.JSONDecodeError:
            raise ValueError("Invalid JSON string")

    raise ValueError("Field must be a dictionary or valid JSON string")
