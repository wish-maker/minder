"""Unit tests for shared.ai.tool_validator.validate_ai_tools.

The plugin-registry aggregates every plugin's AI tools through this helper, so a
single crash here (a manifest shaped unexpectedly) would break tool discovery for
ALL plugins. It defensively extracts only well-formed tool dicts and never raises —
that contract had zero direct coverage. Pure logic, no deps.
"""

import sys
from pathlib import Path

# shared/ is imported as the top-level `shared` package across services (they put
# /app/src on sys.path); mirror that here so `from shared.ai... import ...` resolves.
_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from shared.ai.tool_validator import validate_ai_tools  # noqa: E402

_TOOL = {
    "name": "get_crypto_price",
    "description": "…",
    "parameters": {},
    "action": "x",
}


def test_extracts_ai_tools_list():
    assert validate_ai_tools({"ai_tools": [_TOOL]}) == [_TOOL]


def test_accepts_legacy_tools_key():
    assert validate_ai_tools({"tools": [_TOOL]}) == [_TOOL]


def test_ai_tools_takes_precedence_over_legacy_tools():
    other = {"name": "other"}
    # ai_tools present + non-empty wins over the legacy key.
    assert validate_ai_tools({"ai_tools": [_TOOL], "tools": [other]}) == [_TOOL]


def test_empty_ai_tools_falls_through_to_legacy_tools():
    # `[] or manifest.get("tools")` — an empty ai_tools list is falsy, so the legacy
    # key is used. Lock this real (slightly surprising) behaviour.
    other = {"name": "other"}
    assert validate_ai_tools({"ai_tools": [], "tools": [other]}) == [other]


def test_drops_entries_without_a_name():
    tools = [_TOOL, {"description": "no name"}, {"name": ""}]
    assert validate_ai_tools({"ai_tools": tools}) == [_TOOL]


def test_drops_non_dict_entries():
    tools = [_TOOL, "not-a-dict", 42, None]
    assert validate_ai_tools({"ai_tools": tools}) == [_TOOL]


def test_non_list_tools_is_empty():
    assert validate_ai_tools({"ai_tools": {"name": "x"}}) == []
    assert validate_ai_tools({"ai_tools": "nope"}) == []


def test_missing_keys_is_empty():
    assert validate_ai_tools({}) == []
    assert validate_ai_tools({"unrelated": 1}) == []


def test_manifest_without_get_is_empty():
    # A non-mapping manifest (None, str, list) must not raise.
    assert validate_ai_tools(None) == []
    assert validate_ai_tools("a manifest string") == []
    assert validate_ai_tools([_TOOL]) == []
