# services/marketplace/models/installation.py
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class InstallationStatus(str, Enum):
    """Installation status"""

    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UNINSTALLED = "uninstalled"


class InstallationCreate(BaseModel):
    """Model for creating an installation"""

    user_id: str = Field(
        ..., pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    plugin_id: str = Field(
        ..., pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    version: Optional[str] = None


class InstallationUpdate(BaseModel):
    """Model for updating an installation"""

    status: Optional[InstallationStatus] = None
    enabled: Optional[bool] = None
    config_json: Optional[Dict[str, Any]] = None


class InstallationResponse(BaseModel):
    """Model for installation response"""

    id: str = Field(
        ..., pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    user_id: str = Field(
        ..., pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    plugin_id: str = Field(
        ..., pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
    )
    version: Optional[str]
    status: InstallationStatus
    enabled: bool
    config_json: Optional[Dict[str, Any]]
    installed_at: datetime
    last_updated_at: datetime

    class Config:
        from_attributes = True
