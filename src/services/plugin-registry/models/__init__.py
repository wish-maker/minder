"""Pydantic request/response models for the plugin-registry service."""

from typing import Dict, List, Optional

from pydantic import BaseModel


class PluginInfo(BaseModel):
    """Plugin information"""

    name: str
    version: str
    description: str
    author: str
    status: str = "registered"  # registered, enabled, disabled, error
    enabled: bool = False  # Track if plugin is enabled
    dependencies: List[str] = []
    capabilities: List[str] = []
    data_sources: List[str] = []
    databases: List[str] = []
    registered_at: str
    health_status: str = "unknown"
    last_health_check: Optional[str] = None


class ServiceRegistration(BaseModel):
    """Service registration for service discovery"""

    service_name: str
    service_type: str
    host: str
    port: int
    health_check_url: str = "/health"
    metadata: Dict = {}


class PluginInstallationRequest(BaseModel):
    """Request to install 3rd party plugin"""

    repository: str
    branch: str = "main"
    version: Optional[str] = None
