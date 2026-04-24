"""
Plugin AI Tools Validator
Validates ai_tools section in plugin manifests
"""

import logging
from typing import Any, Dict, List

from pydantic import ValidationError

from .tool_schema import AIToolDefinition, PluginAITools

logger = logging.getLogger(__name__)


def validate_ai_tools(manifest: Dict[str, Any]) -> List[AIToolDefinition]:
    """
    Validate AI tools section in plugin manifest

    Args:
        manifest: Plugin manifest dictionary

    Returns:
        List of validated AIToolDefinition objects

    Raises:
        ValidationError: If ai_tools section is invalid
    """
    ai_tools_section = manifest.get("ai_tools")

    if not ai_tools_section:
        return []

    # Handle both list and dict formats
    if isinstance(ai_tools_section, list):
        tools_data = {"tools": ai_tools_section}
    elif isinstance(ai_tools_section, dict):
        tools_data = ai_tools_section
    else:
        raise ValidationError(f"ai_tools must be a list or dict, got {type(ai_tools_section)}")

    # Validate with Pydantic
    try:
        plugin_tools = PluginAITools(**tools_data)
        logger.info(f"Validated {len(plugin_tools.tools)} AI tools for plugin")
        return plugin_tools.tools
    except ValidationError as e:
        logger.error(f"AI tools validation failed: {e}")
        raise
