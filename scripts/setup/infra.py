"""Infrastructure provisioning — ported from scripts/lib/infra.sh (#7, Stage 2).

Only `create_networks` is ported so far: it is dry-run-gated (the `docker network
create` goes through docker.run(), the existence probe is read-only), so it is
non-destructive under DRY_RUN and cleanly verifiable — like `stop`.

`initialize_database` (aux DB creation) and `initialize_minio` (bucket creation)
run un-gated `docker exec` mutations, but they are idempotent — CREATE/mc mb only
act when the DB/bucket is absent — so they are verified live against a stack where
all already exist (a safe no-op) with the per-item result masked.
"""

import subprocess
import time

from . import config, docker, env, log


def create_networks() -> None:
    log.step("Setting up Docker networks")

    if docker.network_exists(config.NETWORK_NAME):
        log.info(f"Network '{config.NETWORK_NAME}' already exists")
    else:
        docker.run("docker", "network", "create", config.NETWORK_NAME)
        log.success(f"Network '{config.NETWORK_NAME}' created")

    if docker.network_exists(config.MONITORING_NETWORK_NAME):
        log.info(f"Network '{config.MONITORING_NETWORK_NAME}' already exists")
    else:
        docker.run(
            "docker", "network", "create", config.MONITORING_NETWORK_NAME,
            "--driver", "bridge", "--attachable",
        )
        log.success(f"Network '{config.MONITORING_NETWORK_NAME}' created")


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
            ["docker", "exec", postgres, "psql", "-U", "minder", "-c", f"CREATE DATABASE {db};"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        log.detail(f"Created: {db}" if result.returncode == 0 else f"Already exists: {db}")
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
        "rag-documents", "tts-artifacts", "fine-tuning-datasets",
        "model-checkpoints", "plugin-packages", "backup-archives",
    )
    time.sleep(5)  # bash: give MinIO a moment to be fully ready

    minio = docker.container_name("minio")
    # mc already ships in the image; configure the authed 'mydata' alias the loop uses.
    alias = subprocess.run(
        ["docker", "exec", minio, "mc", "alias", "set", "mydata",
         "http://localhost:9000", env.get("MINIO_ROOT_USER"), env.get("MINIO_ROOT_PASSWORD")],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    if alias.returncode != 0:
        log.warn("Could not configure mc 'mydata' alias — skipping bucket creation")
        return

    for bucket in buckets:
        exists = subprocess.run(
            ["docker", "exec", minio, "mc", "ls", f"mydata/{bucket}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
        if exists:
            log.detail(f"Already exists: {bucket}")
            continue
        made = subprocess.run(
            ["docker", "exec", minio, "mc", "mb", f"mydata/{bucket}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if made.returncode == 0:
            log.detail(f"Created: {bucket}")
            if bucket in ("rag-documents", "tts-artifacts", "plugin-packages"):
                subprocess.run(
                    ["docker", "exec", minio, "mc", "anonymous", "set", "download", f"mydata/{bucket}"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                log.detail(f"Set public policy: {bucket}")
        else:
            log.warn(f"Failed to create bucket: {bucket}")
    log.success("MinIO initialisation complete")
