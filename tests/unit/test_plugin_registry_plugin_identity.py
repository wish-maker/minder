"""Unit tests for plugin-registry's core/plugin_identity.py (#747).

read_stable_id reads a plugin's committed `.plugin_id` marker file -- the
stable anchor a rename-detection flow correlates on, since it survives a
`git mv` of the plugin's directory (unlike the directory name itself, or
anything written to the container's filesystem at runtime, since
src/plugins is COPY'd into the image at build time, not a volume).

Loaded via sys.path + a stale-cache clear -- same pattern as
test_plugin_registry_database.py (a bare top-level `core` package collides
with other services' own `core` packages already imported during test
collection otherwise).
"""

import sys
from pathlib import Path

_SERVICE_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "services" / "plugin-registry"
)


def _fresh_import(module_path: str):
    sys.path.insert(0, str(_SERVICE_DIR))
    for stale in list(sys.modules):
        if stale == "core" or stale.startswith("core."):
            del sys.modules[stale]
    import importlib

    return importlib.import_module(module_path)


plugin_identity = _fresh_import("core.plugin_identity")


def test_reads_the_marker_file_content_stripped(tmp_path):
    (tmp_path / plugin_identity.MARKER_FILENAME).write_text(
        "  abc-123-uuid  \n", encoding="utf-8"
    )

    assert plugin_identity.read_stable_id(tmp_path) == "abc-123-uuid"


def test_returns_none_when_no_marker_file_exists(tmp_path):
    assert plugin_identity.read_stable_id(tmp_path) is None


def test_returns_none_for_an_empty_marker_file(tmp_path):
    (tmp_path / plugin_identity.MARKER_FILENAME).write_text("   \n", encoding="utf-8")

    assert plugin_identity.read_stable_id(tmp_path) is None


def test_returns_none_for_a_nonexistent_directory():
    assert plugin_identity.read_stable_id(Path("/definitely/does/not/exist")) is None
