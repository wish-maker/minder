"""Unit tests for marketplace's plugin_id UUID guard (#526).

A non-UUID plugin_id used to reach the asyncpg UUID `id` column and raise,
surfacing as a 500 that leaked the raw driver error. `valid_plugin_id` rejects
it with a clean 404 at the route boundary, before any DB call — mirroring the
valid-but-absent case. Pure logic; loaded by path like the other marketplace
unit tests (#266 harness note).
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_MARKETPLACE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
)
sys.path.insert(0, str(_MARKETPLACE_DIR))
for _stale in list(sys.modules):
    if _stale == "core" or _stale.startswith("core."):
        del sys.modules[_stale]

_spec = importlib.util.spec_from_file_location(
    "_marketplace_validation_under_test", _MARKETPLACE_DIR / "core" / "validation.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

valid_plugin_id = _mod.valid_plugin_id


def test_valid_uuid_passes_through_unchanged():
    uid = "2eeccce2-9aa7-4a7b-b3ab-6a0929736f59"
    assert valid_plugin_id(uid) == uid


def test_non_uuid_raises_clean_404():
    with pytest.raises(HTTPException) as exc:
        valid_plugin_id("not-a-uuid")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Plugin not found"


def test_route_literal_that_isnt_a_uuid_is_404_not_500():
    # e.g. GET /plugins/installed falling through to /plugins/{plugin_id}
    with pytest.raises(HTTPException) as exc:
        valid_plugin_id("installed")
    assert exc.value.status_code == 404


def test_empty_string_rejected():
    with pytest.raises(HTTPException) as exc:
        valid_plugin_id("")
    assert exc.value.status_code == 404
