# services/plugin-state-manager/models/plugin_state.py
"""
Plugin state models for API requests/responses
"""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class PluginState(str, Enum):
    """Plugin state enumeration"""
    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class LicenseTier(str, Enum):
    """License tier enumeration"""
    FREE = "free"
    COMMUNITY = "community"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class PluginStateResponse(BaseModel):
    """Plugin state response model"""
    id: str
    plugin_name: str
    state: PluginState
    license_tier: LicenseTier
    enabled_at: Optional[datetime] = None
    disabled_at: Optional[datetime] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PluginStateListResponse(BaseModel):
    """Plugin state list response"""
    plugins: list[PluginStateResponse]
    count: int


class EnablePluginRequest(BaseModel):
    """Enable plugin request"""
    reason: Optional[str] = None


class DisablePluginRequest(BaseModel):
    """Disable plugin request"""
    reason: Optional[str] = None
    force: bool = False  # Force disable even if required


class UpdatePluginConfigRequest(BaseModel):
    """Update plugin configuration"""
    config: Dict[str, Any]
    metadata: Optional[Dict[str, Any]] = None


class DefaultPluginResponse(BaseModel):
    """Default plugin response"""
    id: str
    plugin_name: str
    priority: int
    auto_enable: bool
    required: bool
    min_tier: LicenseTier
    description: Optional[str] = None
    version: Optional[str] = None
    created_at: datetime


class PluginDependencyResponse(BaseModel):
    """Plugin dependency response"""
    id: str
    plugin_name: str
    depends_on: str
    required: bool
    version_constraint: Optional[str] = None
