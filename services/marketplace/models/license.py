# services/marketplace/models/license.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LicenseCreate(BaseModel):
    """Model for creating a license"""

    user_id: str = Field(..., pattern="^[0-9a-f-]{36}$")
    plugin_id: str = Field(..., pattern="^[0-9a-f-]{36}$")
    tier: str = Field(..., pattern="^(community|professional|enterprise)$")
    valid_until: Optional[datetime] = None


class LicenseValidate(BaseModel):
    """Model for license validation"""

    license_key: str
    plugin_id: str


class LicenseResponse(BaseModel):
    """Model for license response"""

    id: str = Field(..., pattern="^[0-9a-f-]{36}$")
    user_id: str = Field(..., pattern="^[0-9a-f-]{36}$")
    plugin_id: str = Field(..., pattern="^[0-9a-f-]{36}$")
    tier: str
    license_key: str
    valid_from: datetime
    valid_until: Optional[datetime]
    active: bool
    usage_count: int = Field(..., ge=0)
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
