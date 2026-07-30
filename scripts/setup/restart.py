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
        # Validate the name against the compose service list BEFORE acting, so a
        # mistyped/container-style name (e.g. `minder-redis` instead of `redis`)
        # fails loudly with the valid set instead of `docker compose restart`
        # emitting a bare "no such service" — and, under --dry-run, instead of a
        # misleading "✓ Restarted" for a service that doesn't exist. Mirrors the
        # unknown-service error branch in logs/shell. If the list can't be
        # queried (docker down), skip validation and let compose report.
        services = docker.compose_services()
        if services and service not in services:
            log.error(f"Unknown service: {service}")
            log.detail("Valid services:")
            for name in sorted(services):
                log._emit("  " + name)
            return 1
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
