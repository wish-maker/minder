from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime
from enum import Enum


class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"


class HealthResponse(BaseModel):
    service: str
    status: ServiceStatus
    timestamp: datetime = Field(default_factory=datetime.now)
    uptime_seconds: float
    details: Optional[Dict[str, Any]] = None


class PluginManifest(BaseModel):
    name: str
    version: str
    description: str
    author: str
    requires: list[str] = []
    container: Optional[Dict[str, Any]] = None


class ServiceMessage(BaseModel):
    type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
