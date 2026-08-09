# services/marketplace/models/installation.py
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class InstallationStatus(str, Enum):
    """Installation status"""

    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UNINSTALLED = "uninstalled"


class InstallationResponse(BaseModel):
    """Model for installation response"""

    id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    # user_id is an opaque JWT-derived identifier (str(user["id"]), e.g. "4", or
    # the literal "admin") -- NOT a UUID. The UUID pattern here rejected every
    # real value, so install_plugin's response_model=InstallationResponse 500'd
    # on serialization for any real user even after the FK bug (schema.sql) was
    # fixed. Confirmed live via direct construction: ValidationError on "4".
    user_id: str
    plugin_id: str = Field(
        ...,
        pattern="^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    version: Optional[str]
    status: InstallationStatus
    enabled: bool
    config_json: Optional[Dict[str, Any]]
    installed_at: datetime
    last_updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InstalledPluginSummary(BaseModel):
    """One row of `GET /v1/marketplace/installations/me` (#402) -- an
    installation joined with its plugin's metadata, so the client doesn't need
    an N+1 fetch per installed plugin just to show a name/description."""

    installation_id: str
    plugin_id: str
    version: Optional[str]
    status: InstallationStatus
    enabled: bool
    installed_at: datetime
    last_updated_at: datetime
    name: str
    display_name: str
    description: Optional[str]
    current_version: Optional[str]
    pricing_model: str
    base_tier: str
    category_id: Optional[str]
    author: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class MyInstallationsResponse(BaseModel):
    """Response for GET /v1/marketplace/installations/me."""

    installations: List[InstalledPluginSummary]
    count: int
