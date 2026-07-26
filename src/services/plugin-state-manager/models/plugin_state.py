# services/plugin-state-manager/models/plugin_state.py
"""
Plugin state models for API requests/responses
"""

import sys
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

# shared.models lives under /app/src; guard the path so this module imports cleanly
# regardless of import order (main.py/config.py also insert it).
if "/app/src" not in sys.path:
    sys.path.insert(0, "/app/src")

from shared.models.tiers import LicenseTier  # noqa: E402,F401  (re-exported below)


class PluginState(str, Enum):
    """Plugin state enumeration"""

    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


# LicenseTier is the canonical enum from shared.models.tiers, re-exported here so the
# existing `from models.plugin_state import LicenseTier` call sites keep working while
# the vocabulary stays single-sourced across services (#142).


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

    model_config = ConfigDict(from_attributes=True)


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
