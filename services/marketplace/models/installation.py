# services/marketplace/models/installation.py
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class InstallationStatus(str, Enum):
    """Installation status"""

    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UNINSTALLED = "uninstalled"


class InstallationCreate(BaseModel):
    """Model for creating an installation"""

    user_id: str
    plugin_id: str
    version: Optional[str] = None


class InstallationUpdate(BaseModel):
    """Model for updating an installation"""

    status: Optional[InstallationStatus] = None
    enabled: Optional[bool] = None
    config_json: Optional[dict] = None


class InstallationResponse(BaseModel):
    """Model for installation response"""

    id: str
    user_id: str
    plugin_id: str
    version: Optional[str]
    status: str
    enabled: bool
    config_json: Optional[dict]
    installed_at: datetime
    last_updated_at: datetime

    class Config:
        from_attributes = True
