"""
AI Tools Data Models
Enhanced models for AI tools management with configuration and lifecycle
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AIToolType(str, Enum):
    """AI tool types"""

    ANALYSIS = "analysis"
    ACTION = "action"
    QUERY = "query"


class AIToolCategory(str, Enum):
    """AI tool categories"""

    DATA = "data"
    ANALYSIS = "analysis"
    AUTOMATION = "automation"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class ActivationStatus(str, Enum):
    """AI tool activation status"""

    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


class ToolParameterSchema(BaseModel):
    """Tool parameter schema definition"""

    type: str = Field(..., description="Parameter type")
    description: str = Field(..., description="Parameter description")
    enum: Optional[List[str]] = Field(None, description="Allowed values")
    default: Optional[Any] = Field(None, description="Default value")
    required: bool = Field(False, description="Whether parameter is required")
    minimum: Optional[float] = Field(None, description="Minimum value")
    maximum: Optional[float] = Field(None, description="Maximum value")
    pattern: Optional[str] = Field(None, description="Regex pattern")


class AIToolConfigurationCreate(BaseModel):
    """Model for creating AI tool configuration"""

    plugin_id: str
    tool_name: str = Field(..., min_length=1, max_length=100)
    configuration_schema: Dict[str, Any] = Field(..., description="JSON Schema for configuration")
    default_configuration: Dict[str, Any] = Field(..., description="Default configuration values")
    required_parameters: Optional[Dict[str, Any]] = None
    optional_parameters: Optional[Dict[str, Any]] = None


class AIToolConfigurationResponse(BaseModel):
    """Model for AI tool configuration response"""

    id: str
    plugin_id: str
    tool_name: str
    configuration_schema: Dict[str, Any]
    default_configuration: Dict[str, Any]
    required_parameters: Optional[Dict[str, Any]]
    optional_parameters: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIToolRegistrationCreate(BaseModel):
    """Model for creating AI tool registration"""

    plugin_id: str
    tool_name: str
    installation_id: str
    configuration: Dict[str, Any] = Field(default_factory=dict)


class AIToolRegistrationUpdate(BaseModel):
    """Model for updating AI tool registration"""

    configuration: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None
    activation_status: Optional[ActivationStatus] = None


class AIToolRegistrationResponse(BaseModel):
    """Model for AI tool registration response"""

    id: str
    plugin_id: str
    tool_name: str
    installation_id: str
    configuration: Dict[str, Any]
    is_enabled: bool
    activation_status: str
    last_validated_at: Optional[datetime]
    validation_status: Optional[str]
    validation_errors: Optional[Dict[str, Any]]
    usage_count: int
    last_used_at: Optional[datetime]
    registered_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AIToolResponse(BaseModel):
    """Model for AI tool response"""

    id: str
    plugin_id: str
    plugin_name: str
    tool_name: str
    type: str
    description: Optional[str]
    endpoint: str
    method: str
    parameters: Optional[Dict[str, Any]]
    response_format: Optional[Dict[str, Any]]
    required_tier: str
    is_enabled: bool
    category: Optional[str]
    tags: Optional[List[str]]
    configuration_schema: Optional[Dict[str, Any]]
    default_configuration: Optional[Dict[str, Any]]

    class Config:
        from_attributes = True


class PluginAIToolAssignment(BaseModel):
    """Model for assigning AI tool to plugin"""

    tool_id: str
    is_default: bool = False
    required_tier: str = "community"
    configuration_override: Optional[Dict[str, Any]] = None
    is_enabled: bool = True
    display_order: int = 0


class AIToolListResponse(BaseModel):
    """Model for AI tool list response"""

    tools: List[AIToolResponse]
    count: int
    page: int
    page_size: int
    total_pages: int


class AIToolEnableRequest(BaseModel):
    """Model for enabling AI tool"""

    tool_name: str
    configuration: Optional[Dict[str, Any]] = None


class AIToolDisableRequest(BaseModel):
    """Model for disabling AI tool"""

    tool_name: str
    reason: Optional[str] = None


class PluginAIToolsConfig(BaseModel):
    """Model for plugin AI tools configuration"""

    default_enabled: bool = True
    tools: Dict[str, Dict[str, Any]] = Field(default_factory=dict)

    class Config:
        from_attributes = True
