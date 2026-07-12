"""Minder setup — Stage 2 Python port (strangler-fig).

Tracking: issue #7. Goal: port setup.sh (bash) to Python module-by-module for
true cross-platform installs (Linux / macOS / Windows) behind the same CLI,
instead of maintaining parallel bash + PowerShell installers.

Approach (strangler-fig):
- `python -m scripts.setup <verb> [flags]` is the new entrypoint seam. Today it
  delegates to the existing bash `setup.sh` so behaviour is unchanged.
- Each `scripts/lib/<module>.sh` is ported to a Python module here one at a time.
- Every ported module MUST keep `scripts/gate/run-gate.sh` green
  (selfdiff EMPTY / compare identical to the bash baseline) before merge — the
  gate is the behaviour contract. See scripts/setup/README.md.
"""

__version__ = "0.0.1"
