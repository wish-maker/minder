"""`update` verb — ported from scripts/lib/commands.sh cmd_update (#7, Stage 2).

`update --check` → section + version_drift_report (no changes). Full `update` →
pull latest compatible images, rebuild the custom Minder images, and rolling-
restart the running services. The pull/drift come from the ported versions module.
"""

import re
import subprocess
import time

from . import config, docker, log, versions


def _rebuild() -> bool:
    # bash: run compose build --pull --no-cache 2>&1 | tee -a LOG | grep -E 'Step|Successfully|ERROR' || true
    # Under DRY_RUN the [dry-run] echo is piped through the grep, which matches none
    # of Step/Successfully/ERROR → nothing reaches stdout, so this is silent.
    if config.DRY_RUN:
        return True
    try:
        out = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                str(config.COMPOSE_FILE),
                "build",
                "--pull",
                "--no-cache",
            ],
            capture_output=True,
            text=True,
            # Decode as UTF-8 and never raise on stray bytes: docker/buildkit build
            # output carries progress control chars that the platform default codec
            # (cp1252 on Windows) can't decode → text=True alone crashes the whole
            # `update` on Windows with a UnicodeDecodeError. errors="replace" keeps
            # it cross-platform (the shim promises Linux/macOS/Windows).
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        log.error(f"Failed to invoke docker compose build: {exc}")
        return False
    # stdout/stderr can be None if capture failed → guard the concat (was a
    # TypeError: NoneType + str on the crash path above).
    for line in ((out.stdout or "") + (out.stderr or "")).splitlines():
        if re.search(r"Step|Successfully|ERROR", line):
            log._emit(line)
    # #346: a failed build (e.g. a broken registry-credential helper) must not
    # be treated the same as "nothing to rebuild" — the caller used to sail on
    # to the rolling restart regardless, silently keeping whatever images were
    # already local and printing the same "Update complete" either way.
    if out.returncode != 0:
        log.error(
            f"docker compose build exited {out.returncode} — rebuild failed, "
            "existing images were NOT updated"
        )
        return False
    return True


def run(arg: str = "") -> int:
    if arg == "--check":
        log.section("🔍  Update Check  (no changes will be made)")
        log.info("Querying registries…")
        versions.version_drift_report(False)
        return 0

    log.section("🔄  Update Platform")

    versions.pull_all_images()

    log.info("Rebuilding custom Minder images…")
    if not _rebuild():
        log.error(
            "Aborting update — rebuild failed, so a rolling restart would only "
            "recreate containers from stale images while reporting success. "
            "Fix the build error above and re-run './{} update'.".format(
                config.SCRIPT_NAME
            )
        )
        return 1

    log.info("Performing rolling restart…")
    for svc in (
        *config.SECURITY_SERVICES,
        *config.CORE_SERVICES,
        *config.API_SERVICES,
        *config.MONITORING_SERVICES,
        *config.AI_SERVICES,
        "client",
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
