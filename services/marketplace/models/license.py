# services/marketplace/models/license.py
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LicenseCreate(BaseModel):
    """Model for creating a license"""

    user_id: str
    plugin_id: str
    tier: str = Field(..., pattern="^(community|professional|enterprise)$")
    valid_until: Optional[datetime] = None


class LicenseValidate(BaseModel):
    """Model for license validation"""

    license_key: str
    plugin_id: str


class LicenseResponse(BaseModel):
    """Model for license response"""

    id: str
    user_id: str
    plugin_id: str
    tier: str
    license_key: str
    valid_from: datetime
    valid_until: Optional[datetime]
    active: bool
    usage_count: int
    last_used_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
