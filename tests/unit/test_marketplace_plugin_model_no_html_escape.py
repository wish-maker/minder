"""Regression test for PluginCreate/PluginUpdate corrupting text fields.

Found live on hantal: a `field_validator("display_name", "description")`
unconditionally ran `html.escape()` on write, so "&" and "'" were stored as
literal "&amp;"/"&#x27;" and served back that way from every read too --
e.g. the real "network" plugin's description ("...inventories & monitors
found hosts.") came back from `GET /v1/marketplace/plugins` as "...inventories
&amp; monitors found hosts." Nothing in this codebase renders these fields as
raw HTML (the client interpolates them as plain React text, which escapes on
DOM insertion on its own) -- the validator was solving a problem that didn't
exist here, at the cost of corrupting every description containing "&", "'",
"<", or '"'.

Isolated-import pattern matches test_marketplace_install_plugin.py.
"""

import sys
from pathlib import Path

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

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


(plugin_models,) = _isolated_import("models.plugin")


def test_create_preserves_ampersand_and_apostrophe():
    p = plugin_models.PluginCreate(
        name="network",
        display_name="Network",
        description="Autonomous nmap+SNMP discovery; inventories & monitors found hosts.",
        author="Minder",
    )
    assert (
        p.description
        == "Autonomous nmap+SNMP discovery; inventories & monitors found hosts."
    )


def test_create_preserves_apostrophe_in_display_name():
    p = plugin_models.PluginCreate(
        name="x",
        display_name="Verifying #402's install fix",
        author="Minder",
    )
    assert p.display_name == "Verifying #402's install fix"


def test_update_preserves_ampersand():
    u = plugin_models.PluginUpdate(description="A & B")
    assert u.description == "A & B"
