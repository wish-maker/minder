# services/plugin-state-manager/models/tool_execution.py
"""
Tool execution models
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Tool parameter definition"""

    type: str
    description: str
    enum: Optional[list[str]] = None
    default: Optional[Any] = None
    required: bool = False


class ToolSchema(BaseModel):
    """Tool schema definition"""

    name: str
    description: str
    type: str  # analysis, data, action, query
    parameters: Dict[str, ToolParameter]
    response_format: Dict[str, Any]
    endpoint: str
    method: str
    required_tier: str


class ToolDiscoveryResponse(BaseModel):
    """Tool discovery response"""

    tools: list[ToolSchema]
    count: int


class ToolExecutionRequest(BaseModel):
    """Tool execution request"""

    parameters: Dict[str, Any] = Field(default_factory=dict)


class ToolExecutionResponse(BaseModel):
    """Tool execution response"""

    tool_name: str
    plugin_name: str
    result: Any
    execution_time: float
    tier_required: str


class LicenseValidationRequest(BaseModel):
    """License validation request"""

    user_id: str
    tool_name: str


class LicenseValidationResponse(BaseModel):
    """License validation response"""

    allowed: bool
    tier_required: str
    user_tier: str
    reason: Optional[str] = None
