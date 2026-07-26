# services/marketplace/models/license.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from shared.models.tiers import normalize_tier


class LicenseCreate(BaseModel):
    """Model for creating a license"""

    user_id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    plugin_id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    # Canonical tiers: free|community|pro|enterprise. "professional" is accepted as a
    # deprecated alias and normalised to "pro" so a license never gets stored with a
    # spelling the plugin-state-manager's tier gate can't match (#142).
    tier: str = Field(
        ...,
        description="License tier (free|community|pro|enterprise; "
        "'professional' → 'pro' alias)",
    )
    valid_until: Optional[datetime] = None

    @field_validator("tier")
    @classmethod
    def _normalize_tier(cls, v: str) -> str:
        return normalize_tier(v).value


class LicenseValidate(BaseModel):
    """Model for license validation"""

    license_key: str
    plugin_id: str


class LicenseResponse(BaseModel):
    """Model for license response"""

    id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    user_id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    plugin_id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    tier: str
    license_key: str
    valid_from: datetime
    valid_until: Optional[datetime]
    active: bool
    usage_count: int = Field(..., ge=0)
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
