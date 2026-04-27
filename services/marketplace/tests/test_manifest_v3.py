"""
Test Enhanced Plugin Manifest V3 Schema
Tests the comprehensive plugin manifest with AI tools support
"""

import os
from datetime import datetime

import pytest

# Set test environment variables
os.environ.setdefault("MARKETPLACE_DATABASE_HOST", "localhost")
os.environ.setdefault("MARKETPLACE_DATABASE_PORT", "5432")
os.environ.setdefault("MARKETPLACE_DATABASE_USER", "minder")
os.environ.setdefault("MARKETPLACE_DATABASE_PASSWORD", "dev_password_change_me")
os.environ.setdefault("MARKETPLACE_DATABASE_NAME", "minder_marketplace")

from services.marketplace.models.manifest_schema_v3 import (
    EXAMPLE_MANIFEST,
    AIToolCategory,
    AIToolDefinition,
    AIToolType,
    PluginAIConfig,
    PluginManifestV3,
    PluginManifestValidator,
    PluginTier,
)


def test_basic_manifest_creation():
    """Test creating a basic plugin manifest"""
    manifest_data = {
        "name": "test-plugin",
        "display_name": "Test Plugin",
        "description": "A test plugin for validation",
        "version": "1.0.0",
        "author": "Test Author",
        "category": "testing",
    }

    manifest = PluginManifestV3(**manifest_data)

    assert manifest.name == "test-plugin"
    assert manifest.display_name == "Test Plugin"
    assert manifest.tier == PluginTier.COMMUNITY
    assert manifest.is_default_enabled == True


def test_ai_tools_definition():
    """Test AI tools definition within manifest"""
    tool_data = {
        "name": "analysis_tool",
        "display_name": "Analysis Tool",
        "description": "Performs data analysis",
        "tool_type": AIToolType.ANALYSIS,
        "category": AIToolCategory.ANALYSIS,
        "endpoint_path": "/api/v1/analyze",
        "http_method": "POST",
        "required_tier": PluginTier.COMMUNITY,
    }

    tool = AIToolDefinition(**tool_data)

    assert tool.name == "analysis_tool"
    assert tool.tool_type == AIToolType.ANALYSIS
    assert tool.endpoint_path == "/api/v1/analyze"
    assert tool.is_default_enabled == True


def test_plugin_with_ai_tools():
    """Test plugin with AI tools configuration"""
    manifest_data = {
        "name": "ai-plugin",
        "display_name": "AI Plugin",
        "description": "Plugin with AI tools",
        "version": "1.0.0",
        "author": "AI Corp",
        "category": "ai",
        "tier": PluginTier.PROFESSIONAL,
        "ai_tools": {
            "default_enabled": True,
            "tools": [
                {
                    "name": "text_analysis",
                    "display_name": "Text Analysis",
                    "description": "Analyzes text data",
                    "tool_type": AIToolType.ANALYSIS,
                    "endpoint_path": "/api/v1/text-analysis",
                    "required_tier": PluginTier.COMMUNITY,
                },
                {
                    "name": "advanced_ml",
                    "display_name": "Advanced ML",
                    "description": "Advanced machine learning tools",
                    "tool_type": AIToolType.ANALYSIS,
                    "endpoint_path": "/api/v1/advanced-ml",
                    "required_tier": PluginTier.PROFESSIONAL,
                    "requires_configuration": True,
                    "default_configuration": {"model": "gpt-4", "temperature": 0.7},
                },
            ],
        },
    }

    manifest = PluginManifestV3(**manifest_data)

    assert manifest.get_ai_tools_count() == 2
    assert manifest.ai_tools.default_enabled == True

    # Test tool retrieval
    text_tool = manifest.get_tool_by_name("text_analysis")
    assert text_tool is not None
    assert text_tool.required_tier == PluginTier.COMMUNITY

    ml_tool = manifest.get_tool_by_name("advanced_ml")
    assert ml_tool is not None
    assert ml_tool.requires_configuration == True
    assert ml_tool.default_configuration["model"] == "gpt-4"


def test_tier_based_access():
    """Test tier-based access control"""
    manifest_data = {
        "name": "tiered-plugin",
        "display_name": "Tiered Plugin",
        "description": "Plugin with tier-based features",
        "version": "1.0.0",
        "author": "TierCorp",
        "category": "business",
        "tier": PluginTier.PROFESSIONAL,
        "ai_tools": {
            "tools": [
                {
                    "name": "basic_tool",
                    "display_name": "Basic Tool",
                    "description": "Basic functionality",
                    "tool_type": AIToolType.ACTION,
                    "endpoint_path": "/api/basic",
                    "required_tier": PluginTier.COMMUNITY,
                },
                {
                    "name": "pro_tool",
                    "display_name": "Professional Tool",
                    "description": "Professional features",
                    "tool_type": AIToolType.ACTION,
                    "endpoint_path": "/api/pro",
                    "required_tier": PluginTier.PROFESSIONAL,
                },
                {
                    "name": "enterprise_tool",
                    "display_name": "Enterprise Tool",
                    "description": "Enterprise features",
                    "tool_type": AIToolType.ACTION,
                    "endpoint_path": "/api/enterprise",
                    "required_tier": PluginTier.ENTERPRISE,
                },
            ]
        },
    }

    manifest = PluginManifestV3(**manifest_data)

    # Community tier access
    community_tools = manifest.get_tools_by_tier(PluginTier.COMMUNITY)
    assert len(community_tools) == 1
    assert community_tools[0].name == "basic_tool"

    # Professional tier access
    pro_tools = manifest.get_tools_by_tier(PluginTier.PROFESSIONAL)
    assert len(pro_tools) == 2
    assert any(tool.name == "basic_tool" for tool in pro_tools)
    assert any(tool.name == "pro_tool" for tool in pro_tools)

    # Enterprise tier access
    enterprise_tools = manifest.get_tools_by_tier(PluginTier.ENTERPRISE)
    assert len(enterprise_tools) == 3


def test_manifest_validation():
    """Test manifest validation utilities"""
    manifest_data = {
        "name": "valid-plugin",
        "display_name": "Valid Plugin",
        "description": "A properly configured plugin",
        "version": "2.1.0",
        "author": "Valid Author",
        "category": "validation",
        "ai_tools": {
            "tools": [
                {
                    "name": "well_configured_tool",
                    "display_name": "Well Configured Tool",
                    "description": "A tool with proper configuration",
                    "tool_type": AIToolType.QUERY,
                    "endpoint_path": "/api/v1/well-configured",
                    "required_tier": PluginTier.COMMUNITY,
                    "requires_configuration": True,
                    "default_configuration": {"api_key": "default_key"},
                }
            ]
        },
    }

    manifest = PluginManifestV3(**manifest_data)

    # Validate consistency
    warnings = PluginManifestValidator.validate_ai_tools_consistency(manifest)
    assert len(warnings) == 0

    # Check tier compatibility
    compatibility = PluginManifestValidator.check_tier_compatibility(manifest, PluginTier.COMMUNITY)
    assert compatibility["is_compatible"] == True
    assert compatibility["total_tools"] == 1
    assert len(compatibility["available_tools"]) == 1


def test_example_manifest():
    """Test the example manifest loads correctly"""
    manifest = PluginManifestV3(**EXAMPLE_MANIFEST)

    assert manifest.name == "advanced-analytics"
    assert manifest.tier == PluginTier.PROFESSIONAL
    assert manifest.get_ai_tools_count() == 2

    # Check specific tools
    trend_tool = manifest.get_tool_by_name("trend_analysis")
    assert trend_tool is not None
    assert trend_tool.required_tier == PluginTier.COMMUNITY

    predictive_tool = manifest.get_tool_by_name("predictive_modeling")
    assert predictive_tool is not None
    assert predictive_tool.requires_configuration == True
    assert predictive_tool.default_configuration["model_type"] == "random_forest"


def test_manifest_validation_errors():
    """Test manifest validation catches errors"""
    # Invalid plugin name
    with pytest.raises(ValueError) as exc_info:
        PluginManifestV3(
            name="invalid name!",
            display_name="Invalid Plugin",
            description="Plugin with invalid name",
            version="1.0.0",
            author="Test",
            category="test",
        )
    assert "alphanumeric" in str(exc_info.value).lower()

    # Invalid version format
    with pytest.raises(ValueError) as exc_info:
        PluginManifestV3(
            name="test-plugin",
            display_name="Test Plugin",
            description="Test",
            version="invalid",
            author="Test",
            category="test",
        )
    assert "semantic" in str(exc_info.value).lower()


def test_configuration_requirements():
    """Test plugin configuration requirements detection"""
    # Plugin with configuration
    manifest_with_config = PluginManifestV3(
        name="config-plugin",
        display_name="Config Plugin",
        description="Plugin with configuration",
        version="1.0.0",
        author="Test",
        category="test",
        default_configuration={"api_key": "change_me"},
    )

    assert manifest_with_config.requires_configuration() == True

    # Plugin with AI tools requiring configuration
    manifest_with_tools = PluginManifestV3(
        name="tools-plugin",
        display_name="Tools Plugin",
        description="Plugin with tools",
        version="1.0.0",
        author="Test",
        category="test",
        ai_tools={
            "tools": [
                {
                    "name": "tool_with_config",
                    "display_name": "Tool With Config",
                    "description": "Tool requiring configuration",
                    "tool_type": AIToolType.ANALYSIS,
                    "endpoint_path": "/api/tool",
                    "requires_configuration": True,
                    "default_configuration": {"setting": "value"},
                }
            ]
        },
    )

    assert manifest_with_tools.requires_configuration() == True

    # Plugin without configuration requirements
    manifest_simple = PluginManifestV3(
        name="simple-plugin",
        display_name="Simple Plugin",
        description="Simple plugin",
        version="1.0.0",
        author="Test",
        category="test",
    )

    assert manifest_simple.requires_configuration() == False


def test_tag_normalization():
    """Test tag normalization and validation"""
    manifest = PluginManifestV3(
        name="tagged-plugin",
        display_name="Tagged Plugin",
        description="Plugin with tags",
        version="1.0.0",
        author="Test",
        category="test",
        tags=["Data Analysis", " MACHINE LEARNING ", "", "visualization"],
    )

    assert manifest.tags == ["data analysis", "machine learning", "visualization"]


def test_endpoint_path_validation():
    """Test endpoint path validation"""
    tool = AIToolDefinition(
        name="test_tool",
        display_name="Test Tool",
        description="Test",
        tool_type=AIToolType.ACTION,
        endpoint_path="api/v1/test",  # Missing leading slash
    )

    # Should auto-correct to start with /
    assert tool.endpoint_path == "/api/v1/test"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
