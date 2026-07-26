"""Minder setup — the Python setup CLI (bash→Python port, issue #7, DONE).

`python -m scripts.setup <verb> [flags]` is the runtime entrypoint; `setup.sh` is a
thin shim that execs it (the inversion landed with #7 — the original bash lives on as
`setup.bash.sh`, kept only as the behaviour-gate parity reference). One CLI, true
cross-platform installs (Linux / macOS / Windows).

Behaviour contract: every change MUST keep `scripts/gate/run-gate.sh` green (selfdiff
EMPTY / compare identical to the frozen bash baseline) before merge. New post-port
verbs with no bash equivalent (e.g. `bundle`) are deliberate additions the gate does
not cover. See scripts/setup/README.md.
"""

import sys as _sys
from pathlib import Path as _Path

# Put `src/` on the path so the setup CLI can import the shared, stdlib-only bundle
# brain (`shared.bundle_graph`) that the registry API also imports — the same seam the
# services use (/app/src). Done in the package __init__ so it runs before any submodule
# body (e.g. bundles.py's `from shared.bundle_graph import ...`). #65.
_SRC_DIR = _Path(__file__).resolve().parents[2] / "src"
if _SRC_DIR.is_dir() and str(_SRC_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SRC_DIR))

__version__ = "0.0.1"
