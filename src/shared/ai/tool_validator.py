"""
AI Tool Validator

Extracts a plugin's AI tools (for Ollama function-calling) as plain dicts.
"""


def validate_ai_tools(manifest):
    """Extract a manifest's AI tools as a list of plain dicts.

    A tool is ``{name, description, parameters (JSON Schema), action|endpoint,
    method?}`` — the same shape a module plugin declares in its ``AI_TOOLS`` class
    attribute. Accepts either an ``ai_tools`` or legacy ``tools`` key. Only dict
    entries that carry a ``name`` are returned (malformed entries are dropped rather
    than crashing the aggregator).
    """
    if not hasattr(manifest, "get"):
        return []
    tools = manifest.get("ai_tools") or manifest.get("tools") or []
    if not isinstance(tools, list):
        return []
    return [t for t in tools if isinstance(t, dict) and t.get("name")]
