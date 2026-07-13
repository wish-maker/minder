"""`stop` verb — ported from scripts/lib/commands.sh cmd_stop (#7, Stage 2).

Brings the whole stack down (compose_monitoring down), removes the app network,
and — only with `--clean`/`--clean-dangling` — prunes dangling images. Faithful
to the bash original, including the two behaviours that are NOT dry-run-gated:
the `docker network ls` probe and the `docker image prune -f` both run directly
(bash calls them outside run()).

Under DRY_RUN the mutating ops (compose down, network rm) are gated by
docker.run() and print `[dry-run] …`, so plain `stop` is non-destructive there —
which is how it is verified (scripts/gate/stop_verify.sh). The `--clean` prune is
NOT gated, so it is never exercised by the dry-run verify.
"""

import subprocess

from . import config, docker, log


def run() -> int:
    log.step("Stopping all services")

    docker.compose_monitoring("down")

    if docker.network_exists(config.NETWORK_NAME):
        # bash: run docker network rm NAME && log_success || log_warn
        if docker.run("docker", "network", "rm", config.NETWORK_NAME) == 0:
            log.success(f"Network '{config.NETWORK_NAME}' removed")
        else:
            log.warn("Network not removed (may still be in use)")

    if config.CLEAN_DANGLING:
        # NOT dry-run-gated: bash runs `docker image prune -f` directly. Mirror
        # `reclaimed="$(docker image prune -f | grep 'Total reclaimed' || echo 'unknown')"`.
        try:
            out = subprocess.run(
                ["docker", "image", "prune", "-f"], capture_output=True, text=True
            )
            matched = [ln for ln in out.stdout.splitlines() if "Total reclaimed" in ln]
            reclaimed = "\n".join(matched) if matched else "unknown"
        except OSError:
            reclaimed = "unknown"
        log.success(f"Dangling images pruned — {reclaimed}")

    log.success("All services stopped")
    return 0
