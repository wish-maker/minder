"""
Shared Pydantic models package
Common request/response models for Minder services
"""

# Canonical paginated list envelope (#501) — the one list shape every service's
# `list` endpoint returns, so a cross-service client never re-learns the wrapper.
from .pagination import PaginatedList

# Canonical license-tier vocabulary (shared so marketplace and plugin-state-manager
# can't drift — see #142).
from .tiers import TIER_RANK, LicenseTier, normalize_tier, tier_rank

__all__ = [
    # List envelope
    "PaginatedList",
    # License tiers
    "LicenseTier",
    "normalize_tier",
    "tier_rank",
    "TIER_RANK",
]
