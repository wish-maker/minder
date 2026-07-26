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

# Canonical license-tier vocabulary (shared so marketplace and plugin-state-manager
# can't drift — see #142).
from .tiers import TIER_RANK, LicenseTier, normalize_tier, tier_rank

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
    # License tiers
    "LicenseTier",
    "normalize_tier",
    "tier_rank",
    "TIER_RANK",
]
