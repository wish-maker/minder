# Stage 2 — `setup.sh` bash → Python port (#7)

**Why.** `setup.sh` + `scripts/lib/*.sh` are Linux/Pi-centric (bash-isms, tty
assumptions). To install cleanly across **Linux / macOS / Windows** we port the
installer to Python — one interpreter, one CLI — instead of maintaining a
parallel bash + PowerShell pair (double the maintenance + drift).

**Strategy: strangler-fig — COMPLETE.**
- `python -m scripts.setup <verb> [flags]` (`scripts/setup/__main__.py`) is the
  implementation. Every verb is native Python; there is no bash delegate.
- `setup.sh` is now a thin shim that execs `python -m scripts.setup "$@"`, so
  `bash setup.sh <verb>` works unchanged.
- The original bash entrypoint is preserved verbatim as `setup.bash.sh` and lives
  on ONLY as the behavior-gate parity reference (not in the runtime path). The
  `scripts/lib/*.sh` modules likewise remain solely as that reference.

## The behaviour contract — the gate

The bash reference's dry-run behaviour (now `setup.bash.sh`) is pinned by
`scripts/gate/`. It captured the golden trace before the port and still guards
against drift between the Python impl and the frozen bash spec:

```bash
scripts/gate/run-gate.sh baseline   # once: capture setup.bash.sh's behaviour
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

Every verb runs natively in Python (no bash). `setup.sh` is a shim → `python -m
scripts.setup`; unknown commands error + print help natively (no delegate).

- [x] entrypoint (`python -m scripts.setup`; `setup.sh` shim execs it — inversion done)
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
- [x] **`install`** (default, no verb) — native (`install.py`); the full install:
      clear + banner + 11 progress-tracked phases (check_prerequisites → prepare_env
      → create_networks → pull_all_images → initialize_database → initialize_minio
      → start_services → wait_for_services → download_ollama_models → migrate →
      run_health_checks) + success banner. Every phase is a ported+verified step.
      Verified vs cmd_install via `scripts/gate/install_cmd_verify.sh`: the 11 steps
      are stubbed on both sides and install's own output (banner + phase labels in
      order + success banner) is compared — capturing the scaffolding + call order
      without live calls/waits.
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
- [x] **`doctor`** — native (`doctor.py`); deep diagnostics — Docker
      (version/compose/RAM), disk, .env (perms + weak-secret scan), port
      availability, container health, dangling volumes, image version drift.
      Verified vs cmd_doctor under SKIP_VERSION_CHECK (drift → skipped) via
      `scripts/gate/doctor_verify.sh`, STRUCTURALLY: every host-specific reading +
      the issue count are masked; the section order/labels, per-port line count,
      and weak-secret findings (shared repo `.env`) compare. version_drift_report
      now returns the drift count (doctor's `issues`; observably drift is shown once
      — bash re-runs+greps for the same).
- [x] **`update [--check]`** — native (`update.py`); `--check` = version_drift_report;
      full = pull_all_images + rebuild custom images + rolling `compose up --no-deps`
      per running service. Verified vs cmd_update under SKIP_VERSION_CHECK+DRY_RUN
      via `scripts/gate/update_verify.sh` (spinner+sleep disabled). NOTE: bash's
      rolling restart is `run compose up …` (run wrapping the compose FUNCTION), so
      its dry-run echo is the literal "compose up …" (unexpanded); the port mirrors
      that under dry-run and runs real `docker compose` otherwise.
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
- [x] **`backup`** — native (`backup.py`); full platform backup
      (.env + Postgres/Neo4j/InfluxDB/Qdrant/RabbitMQ) → `backups/minder-<ts>.tar.gz`
      + keep-last-7 prune. Faithful to which steps go through the dry-run seam:
      Neo4j/InfluxDB/Qdrant/RabbitMQ are `run`-gated, while `mkdir`/`.env` cp/the
      `pg_dumpall`/the final `tar` are bare (un-gated → run for real even under
      DRY_RUN, exactly like bash). Read-only w.r.t. the platform. Verified under
      `DRY_RUN=1` against the live stack via `scripts/gate/backup_verify.sh`
      (function-level with the spinner stubbed — the infra_verify pattern — so the
      async spinner frames don't interleave; backups/ is stashed aside so the run
      starts empty + prune-safe, then the gate's archives are removed and the
      original restored).
- [x] **`restore [archive]`** — native (`restore.py`); restore .env + Postgres +
      Qdrant + RabbitMQ from a `backups/minder-<ts>.tar.gz` (interactive picker when
      no arg). The restore steps are now DRY_RUN-gated (#55 fixed, in bash + port):
      docker steps via `run`/`docker.run` (echo-only), the .env cp / psql / rabbitmq
      steps behind an explicit DRY_RUN branch (the seam can't carry their stdin
      redirect / result check); the archive extraction stays un-gated (read-only
      temp dir → a dry-run preview is still informative). Qdrant copy-in + extract
      now target the same `/tmp/qdrant.tar.gz` (#56 fixed — was extracting a
      stale/absent `qdrant-backup.tar.gz`). Verified via `scripts/gate/restore_verify.sh`:
      the three non-destructive early exits at CLI level, PLUS a full DRY_RUN restore
      of a crafted archive at the FUNCTION level (spinner stubbed — the backup_verify
      pattern; safe on the live stack because every mutating step is now echo-only).
      The real (non-dry) restore is still exercised by hand on a throwaway stack.
- [x] `log` — DONE (`log.py`): stdout formatting (info/success/warn/error/detail/
      `debug`, `step()` `▸` heading, `section()` MAGENTA box with byte-width padding
      to match bash `printf %-48s`), the `spinner` (daemon-thread animation), the
      `progress` bar (`progress_init`/`progress_next`, verified via
      `scripts/gate/install_deps_verify.sh`), AND now the `logs/setup-<ts>.log`
      file-mirroring + the `_cleanup` epilogue: `_log`/`log_step` append a plain
      `[ts] [LEVEL] msg` / `[STEP] msg` line (ANSI-stripped, `log_detail` writes
      nothing), `LOGS_DIR` is created at import (bash `mkdir -p` at source), and
      `cleanup(exit_code)` (wired in `__main__` for native verbs — NOT the bash
      delegate, which runs its own trap) prints the "unexpected exit" epilogue on a
      non-zero exit. `debug()` is VERBOSE-gated + LOG_FILE-only; its call sites in
      `cache`/`versions` are now wired. Verified via `scripts/gate/log_file_verify.sh`
      (file contents byte-identical after ts-mask; cleanup epilogue with path masked
      — each side truncates its LOG_FILE first since bash + python stamp the same
      second-granularity filename and would otherwise collide in append mode).

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
      (date + hex secrets masked). `fill_env_secrets` also carries the **#57 guard**:
      it refuses to auto-(re)generate secrets while a provisioned stack is running
      (that would desync live redis/minio), aborting exit 1 unless
      `MINDER_ALLOW_SECRET_REGEN=1` — verified for exit/message parity + `.env`
      left untouched (the guard only fires when secrets genuinely need filling, so
      healthy full-`.env` start/restart is unaffected).
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
- [x] `infra` — DONE (`infra.py`): `create_networks` (dry-run-gated, uses the
      shared `docker.network_exists`), `initialize_database` (aux-DB CREATE), and
      `initialize_minio` (bucket creation). Verified via `scripts/gate/infra_verify.sh`:
      create_networks under DRY_RUN; the two init functions live but IDEMPOTENT —
      the CREATE DATABASE / mc-bucket ops are no-ops when the DB/bucket already
      exists, so on a fully-provisioned stack they emit "Already exists" for each
      (mutation-free, confirmed: aux DB count unchanged). The wait spinners + minio
      `sleep 5` are disabled on both sides.

- [x] `health` — DONE (`health.py`): `run_health_checks` (SERVICE_PORTS probes via
      urllib/TCP, human + `--json`; verified STRUCTURALLY via
      `scripts/gate/health_verify.sh`) and `download_ollama_models` (internal:
      wait for the ollama container + pull each OLLAMA_MODELS entry, dry-run-gated;
      external: skip). The latter verified via `scripts/gate/ollama_models_verify.sh`
      (external-skip + internal-pull under DRY_RUN; the live installed-model listing
      is masked). The model-list log reproduces bash's `${models[*]}` newline-join
      (IFS=$'\n\t').

Modules still fully in bash:

- (none) — every `scripts/lib/*.sh` module has a native Python counterpart, and
  `setup.sh` is now a shim over `python -m scripts.setup` (entrypoint inversion
  complete). The bash reference (`setup.bash.sh` + `scripts/lib/*.sh`) is retained
  solely as the behavior-gate parity reference, not in the runtime path.

Verb verification: a ported verb's own output must match `bash setup.bash.sh <verb>`
(the frozen bash reference) after normalizing OS/runtime noise — the wall-clock timestamp, the absolute
`.env` path (OS-specific by design), ANSI/CR, and setup.sh's global
`trap _cleanup EXIT` epilogue (log module, not the verb). See
`scripts/gate/ollama_verify.sh` for the pattern.
