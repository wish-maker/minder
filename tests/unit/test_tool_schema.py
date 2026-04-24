"""
Test AI Tool Schema Validation
"""

import pytest
from pydantic import ValidationError

from src.shared.ai.tool_schema import AIToolDefinition, ParameterType, ToolParameter
from src.shared.ai.tool_validator import validate_ai_tools


def test_tool_parameter_creation():
    """Test creating a valid tool parameter"""
    param = ToolParameter(type=ParameterType.STRING, description="Cryptocurrency symbol", enum=["BTC", "ETH", "SOL"])
    assert param.type == ParameterType.STRING
    assert param.enum == ["BTC", "ETH", "SOL"]


def test_ai_tool_definition():
    """Test creating a valid AI tool definition"""
    tool = AIToolDefinition(
        name="get_crypto_price",
        description="Get current cryptocurrency price",
        endpoint="/analysis",
        method="GET",
        parameters={
            "symbol": ToolParameter(
                type=ParameterType.STRING, description="Cryptocurrency symbol", enum=["BTC", "ETH"], required=True
            )
        },
    )
    assert tool.name == "get_crypto_price"
    assert tool.parameters["symbol"].required is True


def test_validate_ai_tools_from_list():
    """Test validating AI tools from list format"""
    manifest = {
        "ai_tools": [
            {
                "name": "get_crypto_price",
                "description": "Get crypto price",
                "endpoint": "/analysis",
                "method": "GET",
                "parameters": {
                    "symbol": {"type": "string", "description": "Symbol", "enum": ["BTC", "ETH"], "required": True}
                },
            }
        ]
    }
    tools = validate_ai_tools(manifest)
    assert len(tools) == 1
    assert tools[0].name == "get_crypto_price"


def test_validate_ai_tools_empty():
    """Test validating manifest without AI tools"""
    manifest = {}
    tools = validate_ai_tools(manifest)
    assert tools == []


def test_invalid_tool_parameter_type():
    """Test validation fails with invalid parameter type"""
    with pytest.raises(ValidationError):
        ToolParameter(type="invalid_type", description="Test")


def test_missing_required_field():
    """Test validation fails when required field missing"""
    with pytest.raises(ValidationError):
        AIToolDefinition(
            # Missing required 'name' field
            description="Test tool"
        )
