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
- [x] **`start`** — native (`start.py`); the first orchestration verb — calls the
      ported steps in order: check_prerequisites → prepare_env → validate_gpu →
      validate_access_mode → validate_ai_compute_mode →
      validate_compute_resource_profile → create_networks → start_services →
      wait_for_services → run_health_checks. Pure sequencing, so it is verified by
      CALL ORDER vs bash cmd_start (`scripts/gate/start_cmd_verify.sh`, which
      monkeypatches the steps and diffs the order against the bash function body);
      each step body has its own gate script. (A full bash-vs-python run isn't done
      here: the gate's docker shims are bash scripts native-Windows python can't
      exec, and a live run blocks on wait_for_services' no-healthcheck 120s waits;
      on Linux/Pi the shim path works for both.)
- [x] **`status [--json]`** — native (`status.py`); `--json` delegates to
      run_health_checks(json); human mode = section + container-count Summary +
      `docker ps` + `docker stats` tables + health report. Verified vs cmd_status
      via `scripts/gate/status_verify.sh`: --json like health, human STRUCTURALLY
      (counts/statuses/CPU-mem masked; rows reduced to container names; health
      block masked). NOTE: the port emits clean integer counts — bash's
      `grep -c … || echo 0` prints "0\n0" for a zero count (grep -c already emits
      "0" and exits 1, so the `|| echo 0` doubles it), splitting the Summary line;
      the port fixes that (issue #54).
- [x] **`restart`** — native (`restart.py`); `stop` → sleep 3 → `start`, both
      ported verbs. Verified by call order vs bash cmd_restart
      (`scripts/gate/restart_cmd_verify.sh`).
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
- [x] `env` — DONE (`env.py`): `get` (bash `_env_get`, consolidated the
      `ollama.py`/`secrets.py` copies), `gen_secret` (cross-platform
      `secrets.token_hex`, no openssl), `sync_compose_env` (root→compose `.env`
      mirror, raw-byte passthrough for byte-identity), `fill_env_secrets` (secret
      self-heal — SILENT no-op when `.env` is full, the gate-critical property),
      `write_default_env` (fallback `.env`), and `prepare_env` (the orchestration
      install/start call). Verified via `scripts/gate/env_verify.sh`:
      get/gen_secret-format/sync_compose_env-byte, fill selection+log (values are
      random so the log + selection are compared, backup ts normalized), the
      prepare_env full-`.env` SILENT no-op, and write_default_env structure
      (date + hex secrets masked).
- [x] `cache` — DONE (`cache.py`): `cache_file`/`cache_expired`/`load_cached_tags`/
      `cache_tags` (the tag-cache the version engine reads). Verified vs cache.sh
      across path-mapping / fresh-missing-old expiry / parse / write cases via
      `scripts/gate/cache_verify.sh`. Ported ahead of its consumer (the deferred
      versions network layer) — `cache_tags` takes the timestamp as a param
      (deterministic) and writes LF (newline="") to stay byte-identical + cross-OS.
- [x] `versions` — DONE (`versions.py`): the pure core (registry_type/image_repo/
      strip_v/ver_ge/tag_satisfies_constraint/best_tag, 33 cases), the spec
      derivation (compose_image_refs/third_party_image_specs/third_party_images,
      23 specs byte-exact), and the network + orchestration layer (`*_list_tags`
      registry fetches via urllib + cache.py, resolve_image_tag with the
      RESOLVED_IMAGE_TAGS memo, pull_image_with_fallback/pull_all_images,
      version_drift_report human+json). Verified via `scripts/gate/versions_verify.sh`
      + `scripts/gate/versions_net_verify.sh`: pull_all_images + version_drift_report
      on the DETERMINISTIC path (SKIP_VERSION_CHECK+DRY_RUN → resolve short-circuits
      to the pin, no network) — the spinner is disabled on both sides to compare
      the [dry-run] trace + success lines. The live smart-resolution branch is
      ported faithfully but exercised only against real registries. (curl→urllib;
      docker.run gained `quiet=True` to model the pull path's `run … &>/dev/null`.)
- [x] `preflight` — DONE (`preflight.py`): `check_prerequisites`,
      `validate_gpu_environment`, `validate_access_mode` +
      `configure_traefik_access_mode`, `validate_ai_compute_mode`,
      `validate_compute_resource_profile`. Verified via
      `scripts/gate/preflight_verify.sh`: the config validators byte-exact (13
      cases); check_prerequisites structurally (versions/disk/ports masked;
      openssl/curl advisory dropped — Git-Bash vs native-Windows PATH disagree
      here, agree on the Pi); validate_gpu_environment's no-toolkit CPU-fallback
      branch (the `docker run --gpus` fails fast — image not found, no pull);
      validate_access_mode `local` (compares the resulting active traefik-config
      file set — the real side effect — with the files snapshotted + restored)
      and `invalid`.
- [x] `lifecycle` — DONE (`lifecycle.py`): `start_services` (ordered `compose up`
      groups, dry-run-gated; gates the ollama container on the 'internal-ollama'
      profile via OLLAMA_BASE_URL — verified across both ollama branches +
      COMPOSE_PROFILES under DRY_RUN via `scripts/gate/lifecycle_verify.sh`) and
      `wait_for_services` (waits each group healthy — a thin loop over the verified
      wait_healthy + section; composition-verified, and the `start` orchestration
      verify confirms it's invoked in order; a live end-to-end run blocks on
      no-healthcheck 120s timeouts). Needed the service-group arrays (config.py).
- [~] `infra` — partial: `create_networks` ported (`infra.py`), dry-run-gated like
      `stop`, verified via `scripts/gate/infra_verify.sh`. Uses the new shared
      `docker.network_exists` (which also replaced `stop.py`'s local copy).
      Deferred (un-gated mutations + waits, entered only from start/install):
      `initialize_database` (`psql CREATE DATABASE`) and `initialize_minio`
      (`mc mb` buckets).

- [~] `health` — partial: `run_health_checks` ported (`health.py`) — probes each
      SERVICE_PORTS endpoint (urllib HTTP, or TCP for influxdb), human + `--json`
      output. Verified STRUCTURALLY vs health.sh (service set/order/groups/summary)
      via `scripts/gate/health_verify.sh`, masking the live up/down + URLs + counts
      like the gate (curl→urllib, results non-deterministic). Deferred:
      `download_ollama_models` (spinner + `ollama pull`) with cmd_install.

Modules still fully in bash:

- [ ] infra-{db,minio}-init · health-download_ollama_models ·
      commands (backup/restore, doctor, update, install, …)

Verb verification: a ported verb's own output must match `bash setup.sh <verb>`
after normalizing OS/runtime noise — the wall-clock timestamp, the absolute
`.env` path (OS-specific by design), ANSI/CR, and setup.sh's global
`trap _cleanup EXIT` epilogue (log module, not the verb). See
`scripts/gate/ollama_verify.sh` for the pattern.
