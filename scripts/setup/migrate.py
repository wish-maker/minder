"""`migrate` verb — ported from scripts/lib/commands.sh cmd_migrate (#7, Stage 2).

Runs Alembic DB migrations inside the running API containers. These services
create their own schema on startup and ship no Alembic, so each service is only
migrated when `alembic` is actually present in the container — otherwise it is
skipped cleanly (no spurious "migration failed"). Faithful to the bash original:
the `alembic upgrade` call is dry-run-gated via docker.run(); the alembic-probe
`docker exec … command -v alembic` is not (bash runs it directly).

Usage: `migrate [target]` (default target `head`).
"""

import subprocess

from . import config, docker, log

SCRIPT_NAME = config.SCRIPT_NAME

# Order matters — identical to the bash migration_services array.
_MIGRATION_SERVICES = (
    "api-gateway",
    "marketplace",
    "plugin-registry",
    "rag-pipeline",
    "model-management",
)


def _has_alembic(cname: str) -> bool:
    """Mirror: docker exec cname sh -c 'command -v alembic >/dev/null 2>&1'."""
    try:
        result = subprocess.run(
            ["docker", "exec", cname, "sh", "-c", "command -v alembic >/dev/null 2>&1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False
    return result.returncode == 0


def run(target: str = "head") -> int:
    log.section(f"🗄  Database Migration  (target: {target})")

    if not docker.container_running("postgres"):
        log.error("PostgreSQL is not running. Start services first.")
        return 1

    for svc in _MIGRATION_SERVICES:
        if not docker.container_running(svc):
            log.detail(f"{svc} — not running, skipping")
            continue
        cname = docker.container_name(svc)
        if _has_alembic(cname):
            log.info(f"Running migrations in {svc}…")
            # NOTE: bash `| tee -a "$LOG_FILE"` mirrors the alembic OUTPUT to the log
            # file too. log.py's file-mirror only captures log.* messages, not raw
            # subprocess streams, so docker.run() streams alembic to the console only
            # (the console half of tee) — a deliberate, minor fidelity gap.
            if docker.run("docker", "exec", cname, "alembic", "upgrade", target) == 0:
                log.success(f"{svc} — migrations applied")
            else:
                log.warn(f"{svc} — migration failed (check logs)")
        else:
            log.detail(
                f"{svc} — schema self-initialized on startup (no Alembic), skipping"
            )

    log.success("Migration run complete")
    return 0
