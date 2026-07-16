"""`status` verb — ported from scripts/lib/commands.sh cmd_status (#7, Stage 2).

`status --json` → run_health_checks(json). Human mode → a section header, a
container-count Summary, the `docker ps` container table, the `docker stats`
resource table, and the health report. The counts / statuses / CPU-mem-net
readings are live/non-deterministic, so status_verify.sh compares STRUCTURALLY
(container name set + headers + health structure), masking the varying values.
"""

import subprocess

from . import config, health, log

_PREFIX = config.CONTAINER_PREFIX + "-"


def _count(filter_args: list) -> int:
    # docker ps [filter] --format '{{.Names}}' | grep -c "^minder-"
    try:
        out = subprocess.run(
            ["docker", "ps", *filter_args, "--format", "{{.Names}}"],
            capture_output=True,
            text=True,
        ).stdout
    except OSError:
        return 0
    return sum(1 for ln in out.splitlines() if ln.startswith(_PREFIX))


def _filtered(argv: list, keep_first_token: str) -> list:
    # run `docker …`, keep lines containing the header token or a minder- name
    # (bash: `… | grep -E "NAMES|minder-"`), then head.
    try:
        out = subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return []
    return [ln for ln in out.splitlines() if keep_first_token in ln or _PREFIX in ln]


def run(json_mode: bool = False) -> int:
    if json_mode:
        health.run_health_checks(json_mode=True)
        return 0

    log.section("📊  Minder Platform Status")

    total = _count([])
    healthy = _count(["--filter", "health=healthy"])
    unhealthy = _count(["--filter", "health=unhealthy"])
    starting = _count(["--filter", "health=starting"])

    if log._colors_on():
        log._emit(
            f"{log._BOLD}Summary{log._NC}  total={total}  "
            f"{log._GREEN}healthy={healthy}{log._NC}  "
            f"{log._YELLOW}starting={starting}{log._NC}  "
            f"{log._RED}unhealthy={unhealthy}{log._NC}"
        )
    else:
        log._emit(
            f"Summary  total={total}  healthy={healthy}  starting={starting}  unhealthy={unhealthy}"
        )
    log._emit("")

    log._emit(f"{log._BOLD}Containers{log._NC}" if log._colors_on() else "Containers")
    ps_table = _filtered(
        ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        "NAMES",
    )[:30]
    for ln in ps_table:
        log._emit(ln)
    log._emit("")

    log._emit(
        f"{log._BOLD}Resource Usage{log._NC}" if log._colors_on() else "Resource Usage"
    )
    stats_table = _filtered(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}",
        ],
        "NAME",
    )[:20]
    for ln in stats_table:
        log._emit(ln)
    log._emit("")

    health.run_health_checks()
    return 0
