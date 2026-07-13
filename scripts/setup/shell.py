"""`shell` verb — ported from scripts/lib/commands.sh cmd_shell (#7, Stage 2).

`shell [service]` — opens an interactive shell in a running container (bash if
present, else sh). The interactive `docker exec -it` and the no-service prompt
are exercised by hand; the two error branches (no service in non-interactive
mode, container-not-running) are gate-verified (scripts/gate/shell_verify.sh).

Same "(none)" Docker-format quirk as `logs` — see logs.py; reproduced faithfully.
"""

import subprocess
import sys

from . import config, docker, log

SCRIPT_NAME = config.SCRIPT_NAME


def _print_running_list_stripped() -> None:
    # bash: docker ps --format '  {{.Names}}' | grep "^  ${PREFIX}-" \
    #         | sed "s/  ${PREFIX}-/  /" || echo "  (none)"
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "  {{.Names}}"], capture_output=True, text=True
        )
    except OSError:
        out = None
    prefix = f"  {config.CONTAINER_PREFIX}-"
    matched = [ln for ln in out.stdout.splitlines() if ln.startswith(prefix)] if out else []
    if matched:
        for ln in matched:
            # sed "s/  minder-/  /" — first-occurrence prefix strip.
            log._emit(ln.replace(prefix, "  ", 1))
    else:
        log._emit("  (none)")


def run(service: str = "") -> int:
    if not service:
        # echo -e "${BOLD}Running containers:${NC}" (bold header, NO indent —
        # unlike logs' dim, 2-space log_detail header).
        if log._colors_on():
            log._emit(f"{log._BOLD}Running containers:{log._NC}")
        else:
            log._emit("Running containers:")
        _print_running_list_stripped()
        log._emit("")
        if config.INTERACTIVE:
            # printf "…" ; read -r service — interactive, not gate-verified.
            sys.stdout.write(f"Container name (without '{config.CONTAINER_PREFIX}-'): ")
            sys.stdout.flush()
            service = sys.stdin.readline().rstrip("\n")
        else:
            log.error(f"Specify a service: ./{SCRIPT_NAME} shell <service>")
            return 1

    cname = docker.container_name(service)
    try:
        ps = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
        )
        running = ps.stdout.splitlines()
    except OSError:
        running = []
    if cname not in running:
        log.error(f"Container not running: {cname}")
        return 1

    # bash: docker exec -it cname bash --version &>/dev/null || shell="sh"
    shell = "bash"
    probe = subprocess.run(
        ["docker", "exec", "-it", cname, "bash", "--version"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if probe.returncode != 0:
        shell = "sh"

    log.info(f"Opening {shell} in {cname}  (exit to return)")
    return subprocess.run(["docker", "exec", "-it", cname, shell]).returncode
