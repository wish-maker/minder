"""`update` verb — ported from scripts/lib/commands.sh cmd_update (#7, Stage 2).

`update --check` → section + version_drift_report (no changes). Full `update` →
pull latest compatible images, rebuild the custom Minder images, and rolling-
restart the running services. The pull/drift come from the ported versions module.
"""

import re
import subprocess
import time

from . import config, docker, log, versions


def _rebuild() -> None:
    # bash: run compose build --pull --no-cache 2>&1 | tee -a LOG | grep -E 'Step|Successfully|ERROR' || true
    # Under DRY_RUN the [dry-run] echo is piped through the grep, which matches none
    # of Step/Successfully/ERROR → nothing reaches stdout, so this is silent.
    if config.DRY_RUN:
        return
    try:
        out = subprocess.run(
            ["docker", "compose", "-f", str(config.COMPOSE_FILE), "build", "--pull", "--no-cache"],
            capture_output=True, text=True,
        )
    except OSError:
        return
    for line in (out.stdout + out.stderr).splitlines():
        if re.search(r"Step|Successfully|ERROR", line):
            log._emit(line)


def run(arg: str = "") -> int:
    if arg == "--check":
        log.section("🔍  Update Check  (no changes will be made)")
        log.info("Querying registries…")
        versions.version_drift_report(False)
        return 0

    log.section("🔄  Update Platform")

    versions.pull_all_images()

    log.info("Rebuilding custom Minder images…")
    _rebuild()

    log.info("Performing rolling restart…")
    for svc in (
        *config.SECURITY_SERVICES,
        *config.CORE_SERVICES,
        *config.API_SERVICES,
        *config.MONITORING_SERVICES,
        *config.AI_SERVICES,
    ):
        if docker.container_running(svc):
            # bash: `run compose up …` — run wraps the compose FUNCTION name, so
            # under dry-run it echoes the literal args ("compose up …", NOT expanded
            # to `docker compose -f FILE`), while under real it execs the compose fn
            # → docker compose. Mirror both faithfully.
            if config.DRY_RUN:
                docker.run("compose", "up", "-d", "--no-deps", svc)
            else:
                docker.compose("up", "-d", "--no-deps", svc)
            log.detail(f"{svc} restarted")
            time.sleep(2)

    log.success(f"Update complete — run './{config.SCRIPT_NAME} status' to verify")
    return 0
