"""
Enhanced Plugin Manifest V3 Schema
Supports AI tools configuration, tier-based access, and modular plugin architecture
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


class PluginTier(str, Enum):
    """Plugin access tiers"""

    COMMUNITY = "community"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class AIToolType(str, Enum):
    """AI tool types"""

    ANALYSIS = "analysis"
    ACTION = "action"
    QUERY = "query"
    AUTOMATION = "automation"


class AIToolCategory(str, Enum):
    """AI tool categories"""

    DATA = "data"
    ANALYSIS = "analysis"
    AUTOMATION = "automation"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class HttpMethod(str, Enum):
    """HTTP methods for tool endpoints"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class ParameterSchema(BaseModel):
    """Parameter schema definition"""

    type: str = Field(..., description="Parameter type (string, integer, boolean, etc.)")
    description: str = Field(..., description="Parameter description")
    required: bool = Field(False, description="Whether parameter is required")
    default: Optional[Any] = Field(None, description="Default value")
    enum: Optional[List[str]] = Field(None, description="Allowed values")
    minimum: Optional[float] = Field(None, description="Minimum value for numeric types")
    maximum: Optional[float] = Field(None, description="Maximum value for numeric types")
    pattern: Optional[str] = Field(None, description="Regex pattern for string types")


class ToolConfigurationSchema(BaseModel):
    """Tool configuration schema"""

    type: str = Field(default="object", description="Schema type")
    properties: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="Configuration properties"
    )
    required: List[str] = Field(default_factory=list, description="Required configuration keys")


class AIToolDefinition(BaseModel):
    """AI tool definition within plugin manifest"""

    name: str = Field(..., min_length=1, max_length=100, description="Unique tool name")
    display_name: str = Field(
        ..., min_length=1, max_length=200, description="Human-readable tool name"
    )
    description: str = Field(..., min_length=1, max_length=1000, description="Tool description")

    # Tool classification
    tool_type: AIToolType = Field(..., description="Type of AI tool")
    category: AIToolCategory = Field(default=AIToolCategory.CUSTOM, description="Tool category")

    # Endpoint configuration
    endpoint_path: str = Field(..., min_length=1, max_length=500, description="API endpoint path")
    http_method: HttpMethod = Field(default=HttpMethod.POST, description="HTTP method")

    # Schemas
    parameters_schema: Dict[str, ParameterSchema] = Field(
        default_factory=dict, description="Input parameters"
    )
    response_schema: Dict[str, Any] = Field(default_factory=dict, description="Response schema")

    # Configuration
    configuration_schema: ToolConfigurationSchema = Field(
        default_factory=ToolConfigurationSchema, description="Configuration schema"
    )
    default_configuration: Dict[str, Any] = Field(
        default_factory=dict, description="Default configuration"
    )

    # Access control
    required_tier: PluginTier = Field(
        default=PluginTier.COMMUNITY, description="Minimum required tier"
    )
    requires_configuration: bool = Field(
        default=False, description="Whether tool requires configuration"
    )
    allow_user_configuration: bool = Field(default=True, description="Allow users to configure")

    # State
    is_default_enabled: bool = Field(default=True, description="Enable by default")
    display_order: int = Field(default=0, description="Display order in UI")

    # Metadata
    tags: List[str] = Field(default_factory=list, description="Tool tags for filtering")
    version: str = Field(default="1.0.0", description="Tool version")
    author: Optional[str] = Field(None, description="Tool author")

    # Implementation
    implementation_code: Optional[str] = Field(None, description="Inline tool implementation code")
    implementation_file: Optional[str] = Field(None, description="Path to implementation file")

    @field_validator("endpoint_path")
    @classmethod
    def validate_endpoint_path(cls, v: str) -> str:
        """Validate endpoint path starts with /"""
        if not v.startswith("/"):
            v = "/" + v
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Validate and normalize tags"""
        return [tag.lower().strip() for tag in v if tag.strip()]


class PluginAIConfig(BaseModel):
    """Plugin-level AI tools configuration"""

    default_enabled: bool = Field(default=True, description="Enable AI tools by default")
    tools: List[AIToolDefinition] = Field(
        default_factory=list, description="AI tools provided by plugin"
    )

    # Global configuration
    shared_configuration: ToolConfigurationSchema = Field(
        default_factory=ToolConfigurationSchema, description="Shared configuration for all tools"
    )
    shared_defaults: Dict[str, Any] = Field(
        default_factory=dict, description="Default values for shared configuration"
    )


class DependencySpec(BaseModel):
    """Plugin dependency specification"""

    name: str = Field(..., description="Dependency name")
    version: str = Field(..., description="Required version (semver)")
    optional: bool = Field(default=False, description="Whether dependency is optional")


class PluginManifestV3(BaseModel):
    """
    Enhanced Plugin Manifest V3
    Supports comprehensive plugin definition with AI tools, tier-based access, and lifecycle management
    """

    # Basic metadata
    name: str = Field(..., min_length=1, max_length=100, description="Unique plugin identifier")
    display_name: str = Field(..., min_length=1, max_length=200, description="Human-readable name")
    description: str = Field(..., min_length=1, max_length=1000, description="Plugin description")
    version: str = Field(..., min_length=1, max_length=50, description="Plugin version (semver)")

    # Author information
    author: str = Field(..., min_length=1, max_length=200, description="Author name")
    author_email: Optional[str] = Field(None, max_length=200, description="Author email")
    organization: Optional[str] = Field(None, max_length=200, description="Organization name")

    # Classification
    category: str = Field(..., max_length=100, description="Plugin category")
    tags: List[str] = Field(default_factory=list, description="Plugin tags for discovery")
    license: str = Field(default="MIT", max_length=50, description="License type")

    # Access control
    tier: PluginTier = Field(default=PluginTier.COMMUNITY, description="Required access tier")
    pricing: Optional[Dict[str, Any]] = Field(None, description="Pricing information")

    # AI Tools Configuration
    ai_tools: Optional[PluginAIConfig] = Field(None, description="AI tools provided by plugin")

    # Dependencies
    dependencies: List[DependencySpec] = Field(
        default_factory=list, description="Plugin dependencies"
    )
    python_version: str = Field(default=">=3.11", description="Required Python version")

    # Installation
    install_command: Optional[str] = Field(None, description="Custom installation command")
    configuration_schema: ToolConfigurationSchema = Field(
        default_factory=ToolConfigurationSchema, description="Plugin configuration schema"
    )
    default_configuration: Dict[str, Any] = Field(
        default_factory=dict, description="Default plugin configuration"
    )

    # Lifecycle
    requires_restart: bool = Field(
        default=False, description="Whether plugin requires restart after install"
    )
    is_default_enabled: bool = Field(default=True, description="Enable by default")
    can_be_disabled: bool = Field(default=True, description="Allow users to disable")

    # Metadata
    homepage: Optional[str] = Field(None, max_length=500, description="Plugin homepage URL")
    repository: Optional[str] = Field(None, max_length=500, description="Source repository URL")
    documentation: Optional[str] = Field(None, max_length=500, description="Documentation URL")
    logo_url: Optional[str] = Field(None, max_length=500, description="Logo/image URL")
    screenshots: List[str] = Field(default_factory=list, description="Screenshot URLs")

    # Compatibility
    minder_version: str = Field(default=">=1.0.0", description="Compatible Minder version")
    breaking_changes: List[str] = Field(
        default_factory=list, description="List of breaking changes in this version"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate plugin name format"""
        v = v.lower().strip()
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError(
                "Plugin name must contain only alphanumeric characters, hyphens, and underscores"
            )
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        """Validate and normalize tags"""
        return [tag.lower().strip() for tag in v if tag.strip()]

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Basic semantic version validation"""
        parts = v.split(".")
        if len(parts) < 2:
            raise ValueError("Version must follow semantic versioning (e.g., 1.0.0)")
        return v

    def get_ai_tools_count(self) -> int:
        """Get number of AI tools provided by plugin"""
        if self.ai_tools:
            return len(self.ai_tools.tools)
        return 0

    def get_tool_by_name(self, tool_name: str) -> Optional[AIToolDefinition]:
        """Get specific AI tool by name"""
        if self.ai_tools:
            for tool in self.ai_tools.tools:
                if tool.name == tool_name:
                    return tool
        return None

    def get_tools_by_tier(self, tier: PluginTier) -> List[AIToolDefinition]:
        """Get tools available for specific tier"""
        tools = []
        if self.ai_tools:
            tier_order = {
                PluginTier.COMMUNITY: 0,
                PluginTier.PROFESSIONAL: 1,
                PluginTier.ENTERPRISE: 2,
            }
            required_tier_level = tier_order[tier]

            for tool in self.ai_tools.tools:
                tool_tier_level = tier_order[tool.required_tier]
                if tool_tier_level <= required_tier_level:
                    tools.append(tool)
        return tools

    def requires_configuration(self) -> bool:
        """Check if plugin or any of its tools require configuration"""
        if self.default_configuration:
            return True
        if self.ai_tools:
            for tool in self.ai_tools.tools:
                if tool.requires_configuration or tool.default_configuration:
                    return True
        return False


class PluginManifestValidator:
    """Plugin manifest validation utilities"""

    @staticmethod
    def validate_manifest(manifest_data: Dict[str, Any]) -> PluginManifestV3:
        """Validate and create plugin manifest from dictionary"""
        return PluginManifestV3(**manifest_data)

    @staticmethod
    def validate_ai_tools_consistency(manifest: PluginManifestV3) -> List[str]:
        """Validate AI tools consistency within manifest"""
        warnings = []

        if manifest.ai_tools:
            tool_names = set()
            for tool in manifest.ai_tools.tools:
                # Check for duplicate tool names
                if tool.name in tool_names:
                    warnings.append(f"Duplicate tool name: {tool.name}")
                tool_names.add(tool.name)

                # Check if tools with required configuration have defaults
                if tool.requires_configuration and not tool.default_configuration:
                    warnings.append(
                        f"Tool '{tool.name}' requires configuration but has no defaults"
                    )

                # Validate endpoint paths
                if not tool.endpoint_path.startswith("/"):
                    warnings.append(f"Tool '{tool.name}' endpoint path should start with '/'")

        return warnings

    @staticmethod
    def check_tier_compatibility(
        manifest: PluginManifestV3, user_tier: PluginTier
    ) -> Dict[str, Any]:
        """Check if plugin is compatible with user tier"""
        tier_order = {PluginTier.COMMUNITY: 0, PluginTier.PROFESSIONAL: 1, PluginTier.ENTERPRISE: 2}

        plugin_tier_level = tier_order[manifest.tier]
        user_tier_level = tier_order[user_tier]

        is_compatible = user_tier_level >= plugin_tier_level

        available_tools = []
        if manifest.ai_tools:
            for tool in manifest.ai_tools.tools:
                tool_tier_level = tier_order[tool.required_tier]
                if user_tier_level >= tool_tier_level:
                    available_tools.append(tool.name)

        return {
            "is_compatible": is_compatible,
            "plugin_tier": manifest.tier,
            "user_tier": user_tier,
            "available_tools": available_tools,
            "total_tools": manifest.get_ai_tools_count(),
            "restricted_tools": manifest.get_ai_tools_count() - len(available_tools),
        }


# Example usage and documentation
EXAMPLE_MANIFEST = {
    "name": "advanced-analytics",
    "display_name": "Advanced Analytics Plugin",
    "description": "Provides advanced data analysis and visualization tools",
    "version": "1.0.0",
    "author": "DataCorp Inc.",
    "author_email": "plugins@datacorp.example",
    "category": "analytics",
    "tags": ["data", "analysis", "visualization"],
    "license": "MIT",
    "tier": "professional",
    "ai_tools": {
        "default_enabled": True,
        "shared_configuration": {
            "properties": {
                "api_key": {"type": "string", "description": "API key for external services"}
            }
        },
        "tools": [
            {
                "name": "trend_analysis",
                "display_name": "Trend Analysis Tool",
                "description": "Analyzes trends in time series data",
                "tool_type": "analysis",
                "category": "analysis",
                "endpoint_path": "/api/v1/tools/trend-analysis",
                "http_method": "POST",
                "required_tier": "community",
                "parameters_schema": {
                    "data": {"type": "array", "description": "Time series data", "required": True}
                },
                "response_schema": {
                    "type": "object",
                    "properties": {"trends": {"type": "array"}, "confidence": {"type": "number"}},
                },
            },
            {
                "name": "predictive_modeling",
                "display_name": "Predictive Modeling Tool",
                "description": "Advanced ML-based predictions",
                "tool_type": "analysis",
                "category": "analysis",
                "endpoint_path": "/api/v1/tools/predictive-modeling",
                "http_method": "POST",
                "required_tier": "professional",
                "requires_configuration": True,
                "configuration_schema": {
                    "properties": {
                        "model_type": {"type": "string", "description": "Type of ML model"},
                        "accuracy_threshold": {
                            "type": "number",
                            "description": "Minimum accuracy threshold",
                        },
                    },
                    "required": ["model_type"],
                },
                "default_configuration": {"model_type": "random_forest", "accuracy_threshold": 0.8},
            },
        ],
    },
    "dependencies": [
        {"name": "pandas", "version": ">=2.0.0", "optional": False},
        {"name": "scikit-learn", "version": ">=1.3.0", "optional": False},
    ],
    "configuration_schema": {
        "properties": {
            "max_data_points": {
                "type": "integer",
                "description": "Maximum data points for analysis",
            }
        }
    },
    "default_configuration": {"max_data_points": 10000},
    "homepage": "https://datacorp.example/plugins/advanced-analytics",
    "repository": "https://github.com/datacorp/advanced-analytics-plugin",
    "documentation": "https://docs.datacorp.example/advanced-analytics",
}
