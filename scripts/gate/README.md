# setup.sh behavior gate

A dry-run **golden-trace regression harness** for `setup.sh`. It captures a
normalized trace of `setup.sh`'s CLI behavior and lets you prove a change is
**behavior-preserving** — built to verify the Stage 2 bash→Python port (each
ported module must produce the same trace behind the same CLI).

## How it works

For each core verb it runs `setup.sh` under:
- a **PATH shim** (`shim/`) that shadows the real `docker`, `curl`, `wget`, `sleep`
  binaries with deterministic stubs (instant sleep; fixed health/registry reads) —
  so the trace never depends on the live stack, network, or wall-clock;
- **`DRY_RUN=1`** so every mutation is short-circuited (see dependency below);
- **value-only normalization** (`normalize.sed` + two dynamic masks injected by the
  runner): mask values that legitimately vary (timestamps, health results, disk/GPU,
  hostname, absolute repo path); **preserve structure** (command set + order, step
  order, service groups, endpoints).

If two runs differ only in masked values → empty diff. If the command **structure**
changes → the diff shows it. That is the regression signal.

## Usage

```bash
scripts/gate/run-gate.sh selfdiff        # capture twice, diff — MUST be empty (gate on the gate)
scripts/gate/run-gate.sh baseline        # capture current setup.sh -> scripts/gate/.baseline.trace
scripts/gate/run-gate.sh compare         # capture current, diff vs baseline (drift => exit 1)
scripts/gate/run-gate.sh capture <file>  # raw normalized capture to <file>
```

Typical Stage-2 loop: `baseline` on the bash version → port a module → `compare`.
A run takes ~90s (it captures `start`/`restart` twice). Verbs covered:
`--help`, `stop`, `start`, `restart`.

## What it guarantees — and does NOT

**Catches:** changes to the command SET/ORDER, step order, service groups, and
endpoints across the covered verbs. A module that fails to parse, drops a command,
reorders startup, or changes which services/ports it touches → non-empty diff.

**Does NOT catch:** semantic bugs inside a command body that produce the *same*
dry-run trace (e.g. a wrong flag value that still prints the same masked token, or
logic that only manifests against a live daemon). Same residual as `bash -n` /
structure diff — verify those by running for real. The gate proves *structure
preserved*, not *behavior correct*.

## Dependencies & caveats

- **Relies on the `DRY_RUN=1` env-var fix** in `run()` (`scripts/lib/docker.sh`,
  commit 7b0edc7c). If that were reverted, `DRY_RUN=1` would not gate mutations. The
  PATH shim is a backstop (it shadows the real `docker` binary so the gate cannot
  reach a real daemon), but the env-var gate is the primary safety. Proven: a gate
  run leaves real `docker network ls` / container counts unchanged.
- **`influxdb` health uses a raw `>/dev/tcp` bash builtin** (not a binary), so the
  shim cannot intercept it and its branch flaps with live host-port state. The
  normalization collapses both outcomes to one stable token. (`preflight`'s
  busy-port scan is the same class — its advisory line is dropped.) These were found
  via repeated `selfdiff`; an intermittently-empty gate is the dangerous kind, so
  selfdiff is run many times before trusting it.
- **No tracked files are rewritten during a run** (`SNAP_FILES` is empty). This used
  to snapshot/restore `docker/compose/docker-compose.yml` + `.setup/compose.hash`,
  which `regenerate-compose` rewrote outside `run()`. That verb and its machinery were
  removed (#31) — `docker-compose.yml` is now a hand-maintained source, not regenerated,
  so nothing mutates a tracked file during a capture. The `ENV_PATHS` snapshot/seed for
  `.env` (untracked, rewritten by `prepare_env`) is unchanged. A normal run leaves the
  tree clean.

`*.trace` / `.baseline.trace` are gitignored — the **harness** is the durable
artifact; a committed golden trace would go stale and is machine/time-sensitive.
