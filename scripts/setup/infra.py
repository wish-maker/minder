"""Infrastructure provisioning — ported from scripts/lib/infra.sh (#7, Stage 2).

Only `create_networks` is ported so far: it is dry-run-gated (the `docker network
create` goes through docker.run(), the existence probe is read-only), so it is
non-destructive under DRY_RUN and cleanly verifiable — like `stop`.

Deferred (real, un-gated mutations + waits/spinner, entered only from the
still-bash install/start verbs): `initialize_database` (un-gated `psql CREATE
DATABASE` + wait_postgres_ready) and `initialize_minio` (un-gated `mc mb` bucket
creation + wait_healthy).
"""

from . import config, docker, log


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
