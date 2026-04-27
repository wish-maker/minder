"""
AI Tool Schema Definitions
Pydantic models for validating plugin AI tool declarations in manifests
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ParameterType(str, Enum):
    """Supported parameter types"""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class ToolParameter(BaseModel):
    """AI tool parameter definition"""

    type: ParameterType = Field(..., description="Parameter data type")
    description: str = Field(..., description="Parameter description")
    enum: Optional[List[str]] = Field(None, description="Allowed values (for enums)")
    default: Optional[Any] = Field(None, description="Default value")
    required: bool = Field(False, description="Whether parameter is required")


class AIToolDefinition(BaseModel):
    """AI tool definition from plugin manifest"""

    name: str = Field(..., description="Tool name (unique across all plugins)")
    description: str = Field(..., description="Tool description for LLM")
    type: str = Field("analysis", description="Tool type: analysis, action, query")
    endpoint: str = Field(..., description="Plugin endpoint path (e.g., /analysis)")
    method: str = Field("GET", description="HTTP method: GET, POST")
    parameters: Dict[str, ToolParameter] = Field(
        default_factory=dict, description="Tool parameters"
    )
    response_format: Optional[Dict[str, Any]] = Field(
        None, description="Expected response structure"
    )


class PluginAITools(BaseModel):
    """AI tools section in plugin manifest"""

    tools: List[AIToolDefinition] = Field(
        default_factory=list, description="AI tools provided by this plugin"
    )
