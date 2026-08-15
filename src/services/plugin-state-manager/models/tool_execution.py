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
    count: int  # items on this page
    total: int = 0  # total across all pages (#147/C6)
    limit: int = 0
    offset: int = 0


class ToolExecutionRequest(BaseModel):
    """Tool execution request"""

    parameters: Dict[str, Any] = Field(default_factory=dict)
    # A caller-supplied user_id field used to live here (#147/C7, back when "No
    # per-user auth exists in this service yet"). Real JWT auth (Depends(
    # get_current_user_or_service)) is wired into the /execute route now, so a
    # client-controlled identity field is both redundant and unsafe: license/tier
    # checks must run against the VERIFIED caller (current_user["sub"] in
    # routes/tools.py), not whatever user_id a request body happens to name --
    # today's hardcoded "community"-tier stub (core/license.py) makes that inert,
    # but the moment a real per-user tier lookup lands, this field would let any
    # authenticated caller evaluate the tier check as anyone else.


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
