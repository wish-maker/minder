"""`restart` verb — ported from scripts/lib/commands.sh cmd_restart (#7, Stage 2).

No argument → whole-stack restart: stop, pause, start (both halves are ported +
verified verbs). With a service name → restart just that one container via
`docker compose restart <service>` (all profiles activated so monitoring/ollama
services are addressable too). The docs (CLAUDE.md, troubleshooting) document the
per-service form; #123 wired it (it was previously ignored).
"""

import time

from . import docker, log, start, stop


def run(service: str = "") -> int:
    if service:
        log.step(f"Restarting service: {service}")
        rc = docker.compose_all("restart", service)
        if rc == 0:
            log.success(f"Restarted: {service}")
        else:
            log.warn(f"Restart failed for '{service}' (is it a valid service?)")
        return rc
    stop.run()
    time.sleep(3)
    return start.run()
