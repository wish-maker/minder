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

__version__ = "0.0.1"
