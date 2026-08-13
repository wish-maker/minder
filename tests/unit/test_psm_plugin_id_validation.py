"""Unit tests for plugin-state-manager's plugin_id UUID guard (#576).

`GET /v1/tools/plugins/{plugin_id}/tools` queried the marketplace DB's UUID id
column with the raw path value, so a non-UUID plugin_id made asyncpg raise → a
500 ("Plugin tool discovery failed"). `ensure_valid_plugin_id` rejects it with a
clean 404 at the route boundary, before the DB call — the same fix as marketplace
#574/#526.

validation.py imports only uuid + fastapi (no core deps), so it loads by path with
no fakes — matching test_marketplace_plugin_id_validation.py.
"""

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

_PSM_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-state-manager"
)
sys.path.insert(0, str(_PSM_DIR))
for _stale in list(sys.modules):
    if _stale == "core" or _stale.startswith("core."):
        del sys.modules[_stale]

_spec = importlib.util.spec_from_file_location(
    "_psm_validation_under_test", _PSM_DIR / "core" / "validation.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

ensure_valid_plugin_id = _mod.ensure_valid_plugin_id


def test_valid_uuid_passes_through_unchanged():
    uid = "2eeccce2-9aa7-4a7b-b3ab-6a0929736f59"
    assert ensure_valid_plugin_id(uid) == uid


def test_non_uuid_raises_clean_404():
    with pytest.raises(HTTPException) as exc:
        ensure_valid_plugin_id("not-a-uuid")
    assert exc.value.status_code == 404
    assert exc.value.detail == "Plugin not found"


def test_empty_string_rejected():
    with pytest.raises(HTTPException) as exc:
        ensure_valid_plugin_id("")
    assert exc.value.status_code == 404
