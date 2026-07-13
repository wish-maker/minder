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

Ported verbs run natively in Python (no bash); everything else still delegates.

- [x] entrypoint seam (`python -m scripts.setup` → delegates to bash)
- [x] **`help` / `-h` / `--help`** — native (`help.py`); content byte-identical
      to `bash setup.sh --help`
- [x] **`ollama-mode internal|external [url]`** — native (`ollama.py`); flips
      `.env` only. Verified identical to the bash verb across 8 cases (success /
      append / no-change / invalid-url / usage) via `scripts/gate/ollama_verify.sh`
- [x] **`sync-postgres-password`** — native (`secrets.py`); reads `.env`, pushes
      POSTGRES_PASSWORD into the running container via `ALTER USER`. Verified
      identical to the bash verb (no-`.env` / unset-password / live-sync) via
      `scripts/gate/secrets_verify.sh` — the live case re-applies the current
      password (a safe no-op), never writing a synthetic one to the DB.
- [x] **`migrate [target]`** — native (`migrate.py`); runs `alembic upgrade` in
      the API containers that ship Alembic, skips those that self-init their
      schema. Verified identical to the bash verb (default / explicit-head /
      arbitrary-target) via `scripts/gate/migrate_verify.sh` — non-mutating on
      an Alembic-less stack (every service takes the skip branch, so the
      `alembic upgrade` call is never reached).
- [x] **`stop [--clean|--clean-dangling]`** — native (`stop.py`); compose down +
      network rm, optional dangling-image prune. Verified identical to the bash
      verb under `DRY_RUN=1` via `scripts/gate/stop_verify.sh` (non-destructive
      there: the mutating ops are dry-run-gated; the `--clean` prune is not gated
      so it is not exercised by the dry-run verify).
- [x] **`logs [service] [lines]`** — native (`logs.py`); streams one service's or
      all services' logs. Error branch (unknown service) verified via
      `scripts/gate/logs_verify.sh`; the `-f` follow paths stream/block so they
      are exercised by hand.
- [x] **`shell [service]`** — native (`shell.py`); opens bash/sh in a running
      container. Both non-interactive error branches (no service under CI,
      not-running) verified via `scripts/gate/shell_verify.sh`; the interactive
      `docker exec -it` + no-service prompt are exercised by hand.
- [x] **`uninstall [--purge]`** — native (`uninstall.py`); compose down (data
      preserved) or `down -v --remove-orphans` (purge) behind a DESTRUCTIVE
      banner. Verified under `DRY_RUN=1`+`CI` via `scripts/gate/uninstall_verify.sh`
      (both branches — the compose calls are dry-run-gated so nothing is removed;
      the typed-DELETE confirmation is exercised by hand).
- [~] `log` — stdout formatting ported (`log.py`, used by `ollama.py`/`secrets.py`/
      `migrate.py`/`stop.py`); `step()` (the `▸` heading), `section()` (the box
      banner, byte-width padding to match bash `printf %-48s`), and the `spinner`
      (`spinner_start`/`spinner_stop`, a daemon-thread animation used by the wait
      helpers) added. The `logs/*.log` file mirroring + `trap _cleanup EXIT`
      epilogue + the progress bar are deferred to the full module port (they need
      `config`'s LOG_FILE/LOGS_DIR).

Foundation modules (used by the ported verbs; grow as more verbs land):

- [~] `config` — constants the Python side consumes (`config.py`: paths, names,
      DRY_RUN/VERBOSE/CLEAN_DANGLING/INTERACTIVE flags). Kept identical to
      `config.sh` (INTERACTIVE mirrors its tty/CI/NONINTERACTIVE gate); the
      compose-derived image specs / service arrays are added when a verb needs them.
- [~] `docker` — helpers ported (`docker.py`: `run` dry-run seam,
      `container_name/_running/_exists/_health`, `network_exists`,
      `compose`/`compose_monitoring`, and the wait/poll helpers
      `wait_healthy`/`wait_port`/`wait_postgres_ready`).
      Verified live against the running stack (`scripts/gate/docker_verify.sh` +
      `scripts/gate/wait_verify.sh`, positive + negative branches).
      NOTE: `run()`'s dry-run print joins its args with NEWLINES, not spaces —
      setup.sh sets `IFS=$'\n\t'` before sourcing, so bash's `$*` in
      `echo "[dry-run] $*"` uses `\n` as the separator. The real installer prints
      each dry-run arg on its own line; the port matches that. (`docker_verify.sh`
      originally sourced bash under the default IFS, which space-joined and masked
      this — it now sets `IFS=$'\n\t'` to mirror setup.sh.)
- [~] `env` — partial: `get()` (bash `_env_get`), `gen_secret`, and
      `sync_compose_env` (the root→compose `.env` mirror with the DO-NOT-EDIT
      banner) ported (`env.py`). `get` consolidated the duplicate `_env_get`
      copies `ollama.py`/`secrets.py` carried; `gen_secret` uses cross-platform
      `secrets.token_hex` (no openssl); `sync_compose_env` passes the `.env` body
      through as raw bytes (like `cat`) for byte-identity. Verified via
      `scripts/gate/env_verify.sh` (get cases + gen_secret format + sync_compose_env
      byte-compare). Deferred: `prepare_env`/`_fill_env_secrets`/`_write_default_env`
      (the mutating secret self-heal orchestration) with start/install.
- [x] `cache` — DONE (`cache.py`): `cache_file`/`cache_expired`/`load_cached_tags`/
      `cache_tags` (the tag-cache the version engine reads). Verified vs cache.sh
      across path-mapping / fresh-missing-old expiry / parse / write cases via
      `scripts/gate/cache_verify.sh`. Ported ahead of its consumer (the deferred
      versions network layer) — `cache_tags` takes the timestamp as a param
      (deterministic) and writes LF (newline="") to stay byte-identical + cross-OS.
- [~] `versions` — partial: the PURE deterministic core ported (`versions.py`:
      `registry_type`/`image_repo`/`strip_v`/`ver_ge`/`tag_satisfies_constraint`/
      `best_tag`), verified 1:1 vs versions.sh across 33 cases (incl. `sort -V`
      ordering) via `scripts/gate/versions_verify.sh`. The network + orchestration
      layer (`*_list_tags` fetches, `resolve_image_tag`/`pull_*`/
      `version_drift_report`) is deferred — it needs a curl→urllib decision, the
      spinner, RESOLVED_IMAGE_TAGS + THIRD_PARTY_IMAGE_SPECS, and only the
      still-bash install/update/doctor verbs enter it. That layer consumes
      `cache.py`.
- [~] `preflight` — partial: the two PURE Phase-4 config validators ported
      (`preflight.py`: `validate_ai_compute_mode` / `validate_compute_resource_profile`
      — read a mode from `.env` via `env.get`, print the resolved config, export
      the derived vars docker compose reads). Verified vs preflight.sh across 13
      mode/branch cases via `scripts/gate/preflight_verify.sh`. Deferred (env-
      dependent or mutating, entered only from start/install): `check_prerequisites`,
      `validate_gpu_environment`, `validate_access_mode`/`configure_traefik_access_mode`
      (the latter MOVES traefik dynamic config files).
- [~] `lifecycle` — partial: `start_services` ported (`lifecycle.py`) — ordered
      `compose up` groups, dry-run-gated; gates the ollama container on the
      'internal-ollama' compose profile via OLLAMA_BASE_URL. Verified across both
      ollama branches (+ resulting COMPOSE_PROFILES) under DRY_RUN via
      `scripts/gate/lifecycle_verify.sh`. Needed the service-group arrays
      (config.py) + the ported wait_healthy. Deferred: `wait_for_services` (a thin
      loop over the verified wait_healthy; runs live with cmd_start — end-to-end
      verification is impractical, the no-healthcheck services would each block to
      the 120s monitoring timeout).
- [~] `infra` — partial: `create_networks` ported (`infra.py`), dry-run-gated like
      `stop`, verified via `scripts/gate/infra_verify.sh`. Uses the new shared
      `docker.network_exists` (which also replaced `stop.py`'s local copy).
      Deferred (un-gated mutations + waits, entered only from start/install):
      `initialize_database` (`psql CREATE DATABASE`) and `initialize_minio`
      (`mc mb` buckets).

Modules still fully in bash:

- [ ] versions-network-layer · preflight-{prereq,gpu,access} · infra-{db,minio}-init ·
      lifecycle-wait_for_services ·
      commands (status, backup/restore, doctor, update, install, start, …)

Verb verification: a ported verb's own output must match `bash setup.sh <verb>`
after normalizing OS/runtime noise — the wall-clock timestamp, the absolute
`.env` path (OS-specific by design), ANSI/CR, and setup.sh's global
`trap _cleanup EXIT` epilogue (log module, not the verb). See
`scripts/gate/ollama_verify.sh` for the pattern.
