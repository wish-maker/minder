"""`sync-postgres-password` verb — ported from scripts/lib/secrets.sh (#7, Stage 2).

Applies the current `.env` POSTGRES_PASSWORD to the running Postgres container
via `ALTER USER`. This is needed because Postgres bakes the password into its
data volume at first init: editing `.env` alone does NOT rotate the live
credential — this verb pushes the `.env` value into the running database.

Faithful to the bash original, including the two behaviours that are NOT
dry-run-gated: the `docker exec … ALTER USER` runs directly (bash calls it
outside run()), and the SQL role/db are the hardcoded `minder`/`minder`.
"""

import subprocess

from . import config, docker, log

ENV_FILE = config.ENV_FILE
SCRIPT_NAME = config.SCRIPT_NAME


def _env_get(key: str) -> str:
    """Mirror env.sh _env_get: grep -E "^KEY=" .env | cut -d= -f2- (value after '=').

    Local copy for now (matching ollama.py); consolidates into the env-module
    port once env.sh lands.
    """
    try:
        text = ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return ""
    out = [line.split("=", 1)[1] for line in text.splitlines() if line.startswith(f"{key}=")]
    return "\n".join(out)


def sync_postgres_password() -> int:
    if not ENV_FILE.is_file():
        log.error(f"Env file not found: {ENV_FILE}")
        log.detail(f"Run install first: ./{SCRIPT_NAME}")
        return 1

    new_password = _env_get("POSTGRES_PASSWORD")
    if not new_password:
        log.error(f"POSTGRES_PASSWORD not set in {ENV_FILE}")
        return 1

    log.step("Syncing PostgreSQL password from .env")

    if not docker.container_running("postgres"):
        log.warn("PostgreSQL container not running")
        log.detail(f"Start services first: ./{SCRIPT_NAME} start")
        return 1

    log.detail("Applying password from .env to running container…")
    # NOT dry-run-gated: bash runs this docker exec directly (outside run()).
    # &>/dev/null → suppress all output; branch on exit code only.
    result = subprocess.run(
        [
            "docker",
            "exec",
            docker.container_name("postgres"),
            "psql",
            "-U",
            "minder",
            "-d",
            "minder",
            "-c",
            f"ALTER USER minder PASSWORD '{new_password}';",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0:
        log.success("PostgreSQL password synced")
    else:
        log.warn("Password sync failed (may already be set)")
    return 0
