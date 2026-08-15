"""Unit tests for plugin-state-manager tool-parameter validation (#676).

`execute_tool` fetches a tool's own declared parameter schema from marketplace but
historically forwarded the caller's `parameters` to the plugin action verbatim --
missing `required` fields, wrong types, and enum violations were never rejected at
this layer. `_validate_parameters` (a pure function in core.execution) now enforces
required-presence, declared `type` (with lenient string->scalar coercion), and
`enum` membership, raising HTTPException(422) with per-field detail; undeclared keys
stay permissive.

plugin-state-manager is a hyphenated service dir, so `core.execution` is loaded by
path with the collision-prone `core`/`models`/`config` module names snapshotted and
restored so other services' equally named packages aren't poisoned for the run
(same precedent as test_psm_state_transitions / test_marketplace_ai_tools_routes).
"""

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_PSM = Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"
_COLLISION_PRONE_NAMES = ("core", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_PSM))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


(execution,) = _isolated_import("core.execution")


# --- _validate_parameters --------------------------------------------------


def test_empty_schema_forwards_verbatim():
    """A schemaless tool ({}) must preserve today's permissive pass-through."""
    params = {"anything": 1, "goes": "here"}
    assert execution._validate_parameters({}, params) == params


def test_undeclared_keys_are_permissive():
    """Extra keys not in the schema are left alone (optional untyped kwargs)."""
    schema = {"name": {"type": "string"}}
    params = {"name": "x", "extra": 42}
    assert execution._validate_parameters(schema, params) == params


def test_missing_required_field_raises_422():
    schema = {"target": {"type": "string", "required": True}}
    with pytest.raises(HTTPException) as exc:
        execution._validate_parameters(schema, {})
    assert exc.value.status_code == 422
    assert exc.value.detail == [{"field": "target", "error": "field required"}]


def test_present_required_field_passes():
    schema = {"target": {"type": "string", "required": True}}
    assert execution._validate_parameters(schema, {"target": "host"}) == {
        "target": "host"
    }


def test_wrong_type_raises_422():
    schema = {"count": {"type": "integer"}}
    with pytest.raises(HTTPException) as exc:
        execution._validate_parameters(schema, {"count": [1, 2]})
    assert exc.value.status_code == 422
    assert exc.value.detail[0]["field"] == "count"


def test_string_coerced_to_integer():
    schema = {"count": {"type": "integer"}}
    assert execution._validate_parameters(schema, {"count": "5"}) == {"count": 5}


def test_string_coerced_to_number_and_boolean():
    schema = {"ratio": {"type": "number"}, "flag": {"type": "boolean"}}
    out = execution._validate_parameters(schema, {"ratio": "1.5", "flag": "true"})
    assert out == {"ratio": 1.5, "flag": True}


def test_uncoercible_string_raises_422():
    schema = {"count": {"type": "integer"}}
    with pytest.raises(HTTPException) as exc:
        execution._validate_parameters(schema, {"count": "not-a-number"})
    assert exc.value.status_code == 422


def test_bool_rejected_for_integer():
    """bool is a subclass of int -- it must NOT satisfy an integer parameter."""
    schema = {"count": {"type": "integer"}}
    with pytest.raises(HTTPException):
        execution._validate_parameters(schema, {"count": True})


def test_enum_violation_raises_422():
    schema = {"mode": {"type": "string", "enum": ["fast", "slow"]}}
    with pytest.raises(HTTPException) as exc:
        execution._validate_parameters(schema, {"mode": "warp"})
    assert exc.value.status_code == 422
    assert "one of" in exc.value.detail[0]["error"]


def test_enum_valid_passes():
    schema = {"mode": {"type": "string", "enum": ["fast", "slow"]}}
    assert execution._validate_parameters(schema, {"mode": "fast"}) == {"mode": "fast"}


def test_multiple_errors_all_reported():
    """Every violation is reported, not just the first."""
    schema = {
        "a": {"type": "integer", "required": True},
        "b": {"type": "string", "enum": ["x"]},
    }
    with pytest.raises(HTTPException) as exc:
        execution._validate_parameters(schema, {"b": "y"})
    fields = {e["field"] for e in exc.value.detail}
    assert fields == {"a", "b"}


def test_non_dict_spec_is_skipped():
    """A malformed schema entry (non-dict) is ignored, not crashed on."""
    schema = {"weird": "not-a-dict"}
    params = {"weird": "value"}
    assert execution._validate_parameters(schema, params) == params


# --- _coerce_scalar --------------------------------------------------------


def test_coerce_scalar_passthrough_non_string():
    assert execution._coerce_scalar(5, "integer") == 5
    assert execution._coerce_scalar([1], "array") == [1]


def test_coerce_scalar_boolean_variants():
    assert execution._coerce_scalar("yes", "boolean") is True
    assert execution._coerce_scalar("0", "boolean") is False
    with pytest.raises(ValueError):
        execution._coerce_scalar("maybe", "boolean")


def test_coerce_scalar_array_from_json():
    assert execution._coerce_scalar("[1, 2, 3]", "array") == [1, 2, 3]
