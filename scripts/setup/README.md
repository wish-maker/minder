# Stage 2 — `setup.sh` bash → Python port (#7)

**Why.** `setup.sh` + `scripts/lib/*.sh` are Linux/Pi-centric (bash-isms, tty
assumptions). To install cleanly across **Linux / macOS / Windows** we port the
installer to Python — one interpreter, one CLI — instead of maintaining a
parallel bash + PowerShell pair (double the maintenance + drift).

**Strategy: strangler-fig.**
- `python -m scripts.setup <verb> [flags]` is the entrypoint seam
  (`scripts/setup/__main__.py`). Today it delegates to bash `setup.sh`.
- Port each `scripts/lib/<module>.sh` to a Python module here, one at a time.
- When enough modules are Python, the delegate shrinks and finally the bash
  entrypoint is retired — at which point bash is no longer required.

## The behaviour contract — the gate

`setup.sh`'s dry-run behaviour is pinned by `scripts/gate/`. A ported module must
not change the golden trace:

```bash
scripts/gate/run-gate.sh baseline   # once: capture current bash behaviour
# ... port a module ...
scripts/gate/run-gate.sh compare     # MUST be identical to baseline (exit 0)
scripts/gate/run-gate.sh selfdiff    # MUST be EMPTY (determinism)
```

The gate runs under `DRY_RUN=1` + deterministic PATH shims, so it needs no live
stack, and it works on this dev box (verified: selfdiff EMPTY). No ported module
merges unless the gate stays green.

## Module port order (14) — tracked as checkboxes in #7

Dependency order (config first — others read its globals; help/cache last):

`config · log · docker · secrets · cache · versions · preflight · env · infra ·
lifecycle · health · commands · help`

Each module ported to Python emits the same observable behaviour the bash module
does (for data/config modules that other bash modules still consume, the Python
module emits the equivalent shell declarations that `setup.sh` evals — until the
consumers are ported too).

## Status

- [x] entrypoint seam (`python -m scripts.setup` → delegates to bash)
- [ ] config · log · docker · secrets · cache · versions · preflight · env ·
      infra · lifecycle · health · commands · help
