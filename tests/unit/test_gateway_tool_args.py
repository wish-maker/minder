"""Unit tests for the api-gateway tool-call argument normalizer (#chat-tools).

Some models (command-r via Ollama) wrap tool arguments in a
``{"tool_name": ..., "parameters": {...}}`` envelope instead of emitting them flat.
Passing that envelope to a plugin action makes the call fail. `_normalize_tool_args`
unwraps it so those models' tool calls actually execute.

api-gateway is a hyphenated service dir; ai.py imports ``from config import settings``
at module top — a fake config is injected and restored.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

_ROUTE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "api-gateway"
    / "routes"
    / "ai.py"
)


@pytest.fixture
def ai_mod():
    saved = sys.modules.get("config")
    cfg = ModuleType("config")
    cfg.settings = SimpleNamespace(PLUGIN_REGISTRY_URL="http://reg:8001")
    sys.modules["config"] = cfg
    try:
        spec = importlib.util.spec_from_file_location("ai_under_test", _ROUTE)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        yield mod
    finally:
        if saved is not None:
            sys.modules["config"] = saved
        else:
            sys.modules.pop("config", None)


def test_unwraps_parameters_envelope(ai_mod):
    # command-r's shape → the flat args the plugin expects.
    got = ai_mod._normalize_tool_args(
        {"tool_name": "get_crypto_price", "parameters": {"coin": "bitcoin"}}
    )
    assert got == {"coin": "bitcoin"}


def test_bare_parameters_envelope(ai_mod):
    assert ai_mod._normalize_tool_args({"parameters": {"coin": "eth"}}) == {
        "coin": "eth"
    }


def test_flat_args_unchanged(ai_mod):
    assert ai_mod._normalize_tool_args({"coin": "bitcoin"}) == {"coin": "bitcoin"}


def test_non_dict_becomes_empty(ai_mod):
    assert ai_mod._normalize_tool_args(None) == {}
    assert ai_mod._normalize_tool_args("nope") == {}


def test_non_dict_parameters_left_alone(ai_mod):
    # "parameters" that isn't a dict is a real arg, not an envelope — keep as-is.
    args = {"parameters": "raw", "coin": "eth"}
    assert ai_mod._normalize_tool_args(args) == args
