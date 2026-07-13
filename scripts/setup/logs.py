"""`logs` verb — ported from scripts/lib/commands.sh cmd_logs (#7, Stage 2).

`logs [service] [lines]` — streams one service's logs (`docker logs -f`) or all
services' logs (`compose logs -f`). Streaming is interactive/blocking, so only
the "unknown service" error branch is gate-verified (scripts/gate/logs_verify.sh);
the follow paths are ported faithfully but exercised by hand.

Quirk reproduced (NOT a port bug): the "Running containers:" hint runs
`docker ps --format '  {{.Names}}' | grep '^  minder-'`. Some Docker builds
(e.g. Docker Desktop) drop the format's leading spaces, so the grep matches
nothing and the list prints "(none)" even with containers up. The port replicates
the exact command + match, so it prints whatever bash prints on the same Docker.
"""

import subprocess

from . import config, docker, log


def _running_names() -> list[str]:
    """docker ps --format '{{.Names}}' → the running container names."""
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True
        )
    except OSError:
        return []
    return out.stdout.splitlines()


def _print_running_list() -> None:
    # bash: docker ps --format '  {{.Names}}' | grep "^  ${PREFIX}-" || echo "  (none)"
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
            log._emit(ln)
    else:
        log._emit("  (none)")


def run(service: str = "", lines: str = "100") -> int:
    if service:
        cname = docker.container_name(service)
        if cname in _running_names():
            log.info(f"Streaming {service} logs (Ctrl+C to exit)…")
            # Streaming follow — inherits stdio; not gate-verified (blocks on Ctrl+C).
            return subprocess.run(["docker", "logs", "-f", "--tail", lines, cname]).returncode
        log.error(f"No running container: {cname}")
        log.detail("Running containers:")
        _print_running_list()
        return 1

    log.info("Streaming all service logs (Ctrl+C to exit)…")
    return docker.compose("logs", "-f", "--tail", "50")
