"""Stable plugin identity, independent of a plugin's directory name (#747).

A module plugin is correlated to its marketplace catalog row using this
service's own name for it -- which is simply its directory name under
``settings.PLUGINS_PATH`` (see ``plugin_loader.py::load_plugin_from_module``,
``plugin_name = plugin_dir.name``). If that directory is ever renamed (a
`git mv`, since first-party plugins ship in this repo and are baked into the
image at build time -- there is no runtime-writable plugins volume), the
directory name IS the only identity plugin-registry has ever tracked, so
there is no way to notice "this is the same plugin, just renamed" from name
alone: the old row goes stale everywhere, and a new one gets created.

A marker file committed alongside the plugin's own code (``.plugin_id``, a
single UUID) survives a `git mv` intact -- git moves a renamed directory's
full contents, including this file -- so it becomes the actual stable
anchor. This module owns reading it; nothing writes it at runtime, since a
value written to this service's own container filesystem would not survive
the next image rebuild/redeploy (confirmed: `src/plugins` is `COPY`'d into
the image at build time, not a bind-mounted volume) -- it must be a real,
git-committed file for the persistence to mean anything across a rebuild.

A plugin directory with no ``.plugin_id`` yet (one that predates this
change and hasn't been backfilled) simply has no stable identity --
rename-tracking silently does not apply to it until one is added; it still
syncs exactly as before (name-based lookup-or-create).
"""

from pathlib import Path
from typing import Optional

MARKER_FILENAME = ".plugin_id"


def read_stable_id(plugin_dir: Path) -> Optional[str]:
    """Read this plugin's stable id from its committed marker file.

    Returns None if the directory has no marker (not yet backfilled) or the
    file is empty/whitespace-only.
    """
    marker = Path(plugin_dir) / MARKER_FILENAME
    try:
        if not marker.exists():
            return None
        stable_id = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return stable_id or None
