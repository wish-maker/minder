"""Docker helpers — ported from scripts/lib/docker.sh (#7, Stage 2).

The dry-run `run()` seam plus the container-introspection helpers that every
docker verb builds on. Faithful to the bash originals:
  run()               DRY_RUN wrapper: print "[dry-run] <cmd>" and no-op, else exec
  container_name()    "<prefix>-<service>"
  container_running() exact-name match in `docker ps`
  container_health()  `docker inspect` health status, or "n/a"
  container_exists()  exact-name match in `docker ps -a`
  compose()/…         `docker compose -f <file> …` via run()

The wait/poll helpers (wait_healthy/wait_port/wait_postgres_ready) need the
spinner + a live stack and are deferred to a later increment.
"""

import subprocess

from . import config, log


def run(*cmd: object) -> int:
    """Mirror docker.sh run(): dry-run prints the command, else executes it."""
    argv = [str(c) for c in cmd]
    if config.DRY_RUN:
        # bash: echo -e "${DIM}[dry-run] $*${NC}"; return 0
        line = "[dry-run] " + " ".join(argv)
        log._emit(f"{log._DIM}{line}{log._NC}" if log._colors_on() else line)
        return 0
    return subprocess.run(argv).returncode


def container_name(service: str) -> str:
    return f"{config.CONTAINER_PREFIX}-{service}"


def _names(*, all_containers: bool = False) -> list[str]:
    argv = ["docker", "ps", "--format", "{{.Names}}"]
    if all_containers:
        argv.insert(2, "-a")
    try:
        out = subprocess.run(argv, capture_output=True, text=True)
    except OSError:
        return []
    return out.stdout.splitlines()


def container_running(service: str) -> bool:
    return container_name(service) in _names()


def container_exists(service: str) -> bool:
    return container_name(service) in _names(all_containers=True)


def container_health(service: str) -> str:
    # bash: docker inspect --format='{{.State.Health.Status}}' name 2>/dev/null || echo "n/a"
    try:
        out = subprocess.run(
            ["docker", "inspect", "--format={{.State.Health.Status}}", container_name(service)],
            capture_output=True,
            text=True,
        )
    except OSError:
        return "n/a"
    if out.returncode != 0:
        return "n/a"
    val = out.stdout.strip()
    return val or "n/a"


def compose(*args: object) -> int:
    return run("docker", "compose", "-f", config.COMPOSE_FILE, *args)


def compose_monitoring(*args: object) -> int:
    return run("docker", "compose", "-f", config.COMPOSE_FILE, "--profile", "monitoring", *args)
