"""Infrastructure provisioning — ported from scripts/lib/infra.sh (#7, Stage 2).

Only `create_networks` is ported so far: it is dry-run-gated (the `docker network
create` goes through docker.run(), the existence probe is read-only), so it is
non-destructive under DRY_RUN and cleanly verifiable — like `stop`.

`initialize_database` (aux DB creation + UTC session timezone, #252) and
`initialize_minio` (bucket creation) run un-gated `docker exec` mutations, but
they are idempotent — CREATE/mc mb only act when the DB/bucket is absent, and
`ALTER SYSTEM SET timezone` + reload is a safe no-op to repeat — so they are
verified live against a stack where all already exist (a safe no-op) with the
per-item result masked.

`remove_networks` is the `create_networks` counterpart for `uninstall --purge`:
both compose networks are declared `external: true` (see docker-compose.yml), so
`compose down -v` never touches them — confirmed live (2026-08-02): two separate
uninstall --purge runs both left them behind every time. Only called from the
--purge path, matching the destructive tier that already deletes data volumes.

`migrate_volume_names` (#262) is dry-run-gated the same way as `create_networks`
(existence probes read-only, the `docker volume create`/`docker run` mutations go
through docker.run()) and is called from `start`/`install` right before compose
ever touches volumes, so a rename in docker-compose.yml never silently orphans
data already on disk under an old volume name.
"""

import subprocess
import time

from . import config, docker, env, log


def create_networks() -> None:
    log.step("Setting up Docker networks")

    if docker.network_exists(config.NETWORK_NAME):
        log.info(f"Network '{config.NETWORK_NAME}' already exists")
    elif docker.run("docker", "network", "create", config.NETWORK_NAME) == 0:
        log.success(f"Network '{config.NETWORK_NAME}' created")
    else:
        # #348: a failed create used to still log "created" — the failure
        # surfaces anyway on the next `compose up` ("network not found"), but
        # that's a confusing place to first learn about it.
        log.warn(f"Network '{config.NETWORK_NAME}' was NOT created")

    if docker.network_exists(config.MONITORING_NETWORK_NAME):
        log.info(f"Network '{config.MONITORING_NETWORK_NAME}' already exists")
    elif (
        docker.run(
            "docker",
            "network",
            "create",
            config.MONITORING_NETWORK_NAME,
            "--driver",
            "bridge",
            "--attachable",
        )
        == 0
    ):
        log.success(f"Network '{config.MONITORING_NETWORK_NAME}' created")
    else:
        log.warn(f"Network '{config.MONITORING_NETWORK_NAME}' was NOT created")


def remove_networks() -> None:
    log.step("Removing Docker networks")
    for name in (config.NETWORK_NAME, config.MONITORING_NETWORK_NAME):
        if docker.network_exists(name):
            if docker.run("docker", "network", "rm", name) == 0:
                log.success(f"Network '{name}' removed")
            else:
                log.warn(f"Network '{name}' was NOT removed (may still be in use)")
        else:
            log.info(f"Network '{name}' already absent")


# One-time volume-name cleanup (#262): these 9 keys carried a redundant "docker_"
# prefix — Compose auto-prefixes every volume with the project name (`minder`)
# already, so the actual on-disk volumes were double-prefixed (e.g.
# "minder_docker_traefik_letsencrypt"). Old key -> new key, matching the plain
# convention every other volume already uses.
_VOLUME_RENAMES = {
    "docker_traefik_letsencrypt": "traefik_letsencrypt",
    "docker_traefik_logs": "traefik_logs",
    "docker_otel-collector-data": "otel_collector_data",
    "docker_plugins_data": "plugins_data",
    "docker_models_data": "models_data",
    "docker_models_cache": "models_cache",
    "docker_prometheus_data": "prometheus_data",
    "docker_grafana_data": "grafana_data",
    "docker_alertmanager_data": "alertmanager_data",
}

# Same idea as _VOLUME_RENAMES, but the OLD name is bare (no CONTAINER_PREFIX at
# all) rather than "minder_docker_<key>" -- openwebui_data/qdrant_data were
# created bare-named on the Pi at some point predating the rest of that stack
# (every other volume there is correctly "minder_<name>"). Found live (#408):
# a container recreate silently created a NEW, empty "minder_openwebui_data"
# instead of reusing the real one, orphaning 1.1GB of real data -- `external:
# true` with a hardcoded name (the first fix attempt) turned out to not
# generalize to a second real host (hantal) that never had a bare volume at
# all, so a plain `docker compose up` there would hit "external volume ...
# not found". This migration is the actually-general fix: on a host with the
# bare legacy volume, copy it in once; on any host without one (a fresh
# install, or hantal), it's a no-op and Compose creates the standard-named
# volume itself, same as any other `driver: local` volume.
_BARE_VOLUME_RENAMES = {
    "openwebui_data": "openwebui_data",
    "qdrant_data": "qdrant_data",
}


def _migrate_one_volume(old_name: str, new_name: str, label: str) -> "bool | None":
    """Copy `old_name` -> `new_name` via a throwaway alpine container.

    Returns True on a real migration, False on a failed one, None when there
    was nothing to do (old absent, or new already present).
    """
    if not docker.volume_exists(old_name) or docker.volume_exists(new_name):
        return None  # nothing to migrate, or already migrated
    log.info(f"Migrating volume '{old_name}' → '{new_name}'…")
    create_ok = docker.run("docker", "volume", "create", new_name) == 0
    copy_ok = (
        create_ok
        and docker.run(
            "docker",
            "run",
            "--rm",
            "-v",
            f"{old_name}:/from",
            "-v",
            f"{new_name}:/to",
            "alpine",
            "sh",
            "-c",
            "cp -a /from/. /to/",
        )
        == 0
    )
    if copy_ok:
        log.success(f"Migrated: {label}")
        return True
    # #348: this used to log "Migrated" unconditionally — a failed copy (disk
    # full, alpine pull failure, permission error) left `new_name` empty while
    # the docstring's own advice ("remove manually once the new ones look
    # right") could lead an operator who trusted the false success to delete
    # `old_name`, the only good copy of the data.
    log.error(
        f"Failed to migrate volume: {label} — '{old_name}' was NOT copied, do not delete it"
    )
    # If `create_ok`, `new_name` now exists but is empty/partial. Left alone, the
    # `docker.volume_exists(new_name)` check at the top of this function would
    # treat a RETRY of this same migration as "already migrated" and silently
    # skip it forever -- `compose up` then runs against that empty volume with
    # no further error, which for real data is operationally equivalent to data
    # loss (the real data sits untouched in `old_name`, but nothing ever uses it
    # again and nothing flags this a second time). Clean it up so a retry after
    # fixing the underlying issue (disk space, alpine pull, permissions) can
    # actually attempt the copy again.
    if create_ok:
        if docker.run("docker", "volume", "rm", new_name) != 0:
            log.warn(
                f"Could not remove the empty/partial volume '{new_name}' after the "
                "failed copy -- remove it manually before retrying this migration."
            )
    return False


def migrate_volume_names() -> None:
    """#262: copy data from each old (project-prefixed) volume to its renamed
    counterpart before `compose up` ever gets a chance to create an empty volume
    under the new name — without this, a host that already has data under an old
    name (the Pi) would silently lose access to it the moment docker-compose.yml's
    volume keys changed. Idempotent (checks existence both sides) and safe to run
    on every start/restart: a no-op on a fresh install (no old volume) and a no-op
    once already migrated (new volume already exists). Never deletes the old
    volume — that's a manual step once the new one is confirmed good.

    Also covers _BARE_VOLUME_RENAMES (#408/#414): same idea, but the old name has
    no CONTAINER_PREFIX at all (openwebui_data/qdrant_data were created bare on
    the Pi, unlike every project-prefixed volume elsewhere).
    """
    log.step("Checking for volume-name migrations")
    migrated_any = False
    failed = []
    for old_key, new_key in _VOLUME_RENAMES.items():
        old_name = f"{config.CONTAINER_PREFIX}_{old_key}"
        new_name = f"{config.CONTAINER_PREFIX}_{new_key}"
        result = _migrate_one_volume(old_name, new_name, f"{old_key} → {new_key}")
        if result is True:
            migrated_any = True
        elif result is False:
            failed.append(old_key)
    for old_name, new_key in _BARE_VOLUME_RENAMES.items():
        new_name = f"{config.CONTAINER_PREFIX}_{new_key}"
        result = _migrate_one_volume(old_name, new_name, f"{old_name} → {new_name}")
        if result is True:
            migrated_any = True
        elif result is False:
            failed.append(old_name)
    if failed:
        raise SystemExit(1)
    if migrated_any:
        log.detail(
            "Old volume(s) left in place — remove manually once the new ones look right."
        )
    else:
        log.info("No volume migrations needed")


def initialize_database() -> None:
    """bash initialize_database: bring up postgres, then CREATE each auxiliary DB
    (idempotent — "Already exists" when present)."""
    log.step("Initialising databases")
    docker.compose("up", "-d", "postgres")
    if not docker.wait_postgres_ready():
        raise SystemExit(1)  # bash: wait_postgres_ready || exit 1

    log.info("Creating auxiliary databases…")
    postgres = docker.container_name("postgres")
    for db in config.EXTRA_DATABASES:
        # NOT dry-run-gated (bash runs the docker exec directly). Idempotent:
        # CREATE succeeds when absent → "Created", fails when present → "Already exists".
        result = subprocess.run(
            [
                "docker",
                "exec",
                postgres,
                "psql",
                "-U",
                "minder",
                "-c",
                f"CREATE DATABASE {db};",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.detail(
            f"Created: {db}" if result.returncode == 0 else f"Already exists: {db}"
        )

    # Cluster-wide default session timezone (#252): DEFAULT NOW() on a
    # TIMESTAMP (no tz) column casts the tz-aware "now" using the session's
    # `timezone` GUC — left at its OS default this stores local wall-clock
    # (e.g. TR time on the Pi), disagreeing with the naive-UTC values Python
    # writes (#239). ALTER SYSTEM + reload is idempotent and takes effect
    # immediately, so it's safe to run on every install/re-run, including
    # against clusters whose data directory predates this fix.
    # Two separate -c flags, NOT one semicolon-joined string: psql's simple
    # query protocol implicitly wraps a multi-statement -c string in one
    # transaction block, and ALTER SYSTEM cannot run inside a transaction
    # block (confirmed live — a single joined -c errors with exactly that).
    tz_result = subprocess.run(
        [
            "docker",
            "exec",
            postgres,
            "psql",
            "-U",
            "minder",
            "-c",
            "ALTER SYSTEM SET timezone TO 'UTC';",
            "-c",
            "SELECT pg_reload_conf();",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log.detail(
        "Database timezone set to UTC"
        if tz_result.returncode == 0
        else "Could not set database timezone to UTC"
    )

    log.success("Database initialisation complete")


def initialize_minio() -> None:
    """bash initialize_minio: bring up minio, then create each required bucket
    (idempotent — skipped when it already exists), setting a public policy on the
    download buckets."""
    log.step("Initialising MinIO object storage")

    try:
        compose_text = config.COMPOSE_FILE.read_text(encoding="utf-8")
    except OSError:
        compose_text = ""
    if "minio:" not in compose_text:  # grep -q "minio:"
        log.info("MinIO service not defined in docker-compose.yml - skipping")
        return

    docker.compose("up", "-d", "minio")
    if not docker.wait_healthy("minio", config.TIMEOUT_SERVICES):
        raise SystemExit(1)

    log.info("Creating MinIO buckets…")
    buckets = (
        "rag-documents",
        "tts-artifacts",
        "fine-tuning-datasets",
        "model-checkpoints",
        "plugin-packages",
        "backup-archives",
    )
    time.sleep(5)  # bash: give MinIO a moment to be fully ready

    minio = docker.container_name("minio")
    # mc already ships in the image; configure the authed 'mydata' alias the loop uses.
    alias = subprocess.run(
        [
            "docker",
            "exec",
            minio,
            "mc",
            "alias",
            "set",
            "mydata",
            "http://localhost:9000",
            # Match compose's `${MINIO_ROOT_USER:-minioadmin}` default: when the var
            # is unset/empty in .env the container runs as `minioadmin`, so mc must
            # authenticate as that too — else `mc mb` gets Access Denied and every
            # bucket silently fails to create (surfaced on the Pi clean-install, #8).
            env.get("MINIO_ROOT_USER") or "minioadmin",
            env.get("MINIO_ROOT_PASSWORD"),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if alias.returncode != 0:
        log.warn("Could not configure mc 'mydata' alias — skipping bucket creation")
        return

    for bucket in buckets:
        exists = (
            subprocess.run(
                ["docker", "exec", minio, "mc", "ls", f"mydata/{bucket}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ).returncode
            == 0
        )
        if exists:
            log.detail(f"Already exists: {bucket}")
            continue
        made = subprocess.run(
            ["docker", "exec", minio, "mc", "mb", f"mydata/{bucket}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if made.returncode == 0:
            log.detail(f"Created: {bucket}")
            if bucket in ("rag-documents", "tts-artifacts", "plugin-packages"):
                subprocess.run(
                    [
                        "docker",
                        "exec",
                        minio,
                        "mc",
                        "anonymous",
                        "set",
                        "download",
                        f"mydata/{bucket}",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                log.detail(f"Set public policy: {bucket}")
        else:
            log.warn(f"Failed to create bucket: {bucket}")
    log.success("MinIO initialisation complete")
