"""Docker helpers — ported from scripts/lib/docker.sh (#7, Stage 2).

The dry-run `run()` seam plus the container-introspection helpers that every
docker verb builds on. Faithful to the bash originals:
  run()               DRY_RUN wrapper: print "[dry-run] <cmd>" and no-op, else exec
  container_name()    "<prefix>-<service>"
  container_running() exact-name match in `docker ps`
  container_health()  `docker inspect` health status, or "n/a"
  container_exists()  exact-name match in `docker ps -a`
  compose()/…         `docker compose -f <file> …` via run()

The wait/poll helpers (wait_healthy/wait_port/wait_postgres_ready) are also here.
"""

import socket
import subprocess
import time

from . import config, log


def run(*cmd: object, quiet: bool = False) -> int:
    """Mirror docker.sh run(): dry-run prints the command, else executes it.

    quiet=True models a caller's `run … &>/dev/null` (e.g. pull_image_with_fallback,
    backup/restore): under DRY_RUN it suppresses the [dry-run] echo too, and under
    real mode it discards the command's stdout/stderr."""
    argv = [str(c) for c in cmd]
    if config.DRY_RUN:
        if quiet:
            return 0
        # bash: echo -e "${DIM}[dry-run] $*${NC}"; return 0
        # setup.sh sets IFS=$'\n\t' (line 24) BEFORE sourcing, so `$*` joins the
        # args with a NEWLINE (IFS's first char), not a space — the real installer
        # prints each dry-run arg on its own line. Match that byte-for-byte. (The
        # DIM…NC wraps the whole multi-line block: DIM once at the front, NC once
        # at the end.)
        line = "[dry-run] " + "\n".join(argv)
        log._emit(f"{log._DIM}{line}{log._NC}" if log._colors_on() else line)
        return 0
    if quiet:
        return subprocess.run(
            argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        ).returncode
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


def running_names() -> list[str]:
    """Running container names (`docker ps --format {{.Names}}`) — the shared query
    the status/logs/shell verbs use instead of each re-spawning `docker ps`."""
    return _names()


def container_running(service: str) -> bool:
    return container_name(service) in _names()


def capture(argv: list) -> str:
    """Run argv and return its stdout (text), or "" on OSError. Ungated read-only
    capture (bash `$(cmd)`), shared by doctor/health/preflight/status/versions."""
    try:
        return subprocess.run(argv, capture_output=True, text=True).stdout
    except OSError:
        return ""


def cmd_ok(argv: list) -> bool:
    """True iff argv runs and exits 0 (bash `cmd &>/dev/null`); False on OSError.
    Shared by health/preflight for probe commands."""
    try:
        return (
            subprocess.run(
                argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode
            == 0
        )
    except OSError:
        return False


def tcp_open(host: str, port: "int | str", timeout: float = 2) -> bool:
    """True if a TCP connect to host:port succeeds within `timeout`s. Shared by the
    health/doctor port probes (bash `>/dev/tcp/host/port`)."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def has_healthcheck(service: str) -> bool:
    """True if the container defines a Docker healthcheck. Used to avoid waiting the
    full timeout on no-healthcheck-by-design services (otel-collector, exporters) —
    polling their health is futile (it stays 'n/a' forever)."""
    try:
        out = subprocess.run(
            [
                "docker",
                "inspect",
                "--format={{if .State.Health}}yes{{end}}",
                container_name(service),
            ],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return out.returncode == 0 and out.stdout.strip() == "yes"


def container_exists(service: str) -> bool:
    return container_name(service) in _names(all_containers=True)


def container_health(service: str) -> str:
    # bash: docker inspect --format='{{.State.Health.Status}}' name 2>/dev/null || echo "n/a"
    try:
        out = subprocess.run(
            [
                "docker",
                "inspect",
                "--format={{.State.Health.Status}}",
                container_name(service),
            ],
            capture_output=True,
            text=True,
        )
    except OSError:
        return "n/a"
    if out.returncode != 0:
        return "n/a"
    val = out.stdout.strip()
    return val or "n/a"


def network_exists(name: str) -> bool:
    # bash idiom (inlined in create_networks + cmd_stop):
    #   docker network ls --format '{{.Name}}' | grep -q "^name$"
    try:
        out = subprocess.run(
            ["docker", "network", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return name in out.stdout.splitlines()


# ── Wait / poll helpers (docker.sh) ───────────────────────────────────────
# Live polls (not dry-run-gated, read-only). They use the spinner; the spinner
# output is normalized away by the gate, so what's verified is the final
# success/warn/error line + return value.


def wait_healthy(service: str, timeout: int = config.TIMEOUT_SERVICES) -> bool:
    """bash wait_healthy: poll container_health every 3s until healthy or timeout.

    The spinner shows elapsed/timeout so a multi-minute wait reads as progress, not
    a hang. Improvement over the bash reference (product-only; the gate's docker
    shim reports everything healthy so the first poll always wins and the new
    no-healthcheck branch is never reached under the gate): if a container has NO
    healthcheck, its status is 'n/a' forever, so waiting the full timeout is
    pointless — detect that and stop immediately instead of burning the timeout."""
    log.spinner_start(f"Waiting for {service}…")
    elapsed = 0
    while elapsed < timeout:
        if container_health(service) == "healthy":
            log.spinner_stop()
            log.success(f"{service} is healthy")
            return True
        if not has_healthcheck(service):
            log.spinner_stop()
            log.detail(f"{service} — no healthcheck defined, not waiting")
            return True
        time.sleep(3)
        elapsed += 3
        log.spinner_start(f"Waiting for {service}…  ({elapsed}s/{timeout}s)")
    log.spinner_stop()
    log.warn(
        f"{service} not healthy after {timeout}s  (status: {container_health(service)})"
    )
    return False


def wait_port(host: str, port: int, timeout: int = config.TIMEOUT_PORT) -> bool:
    """bash wait_port: poll a TCP connect every 2s (bash uses >/dev/tcp)."""
    elapsed = 0
    while elapsed < timeout:
        try:
            with socket.create_connection((host, int(port)), timeout=2):
                return True
        except OSError:
            pass
        time.sleep(2)
        elapsed += 2
    return False


def wait_postgres_ready(timeout: int = config.TIMEOUT_DB) -> bool:
    """bash wait_postgres_ready: poll `pg_isready -U minder` every 2s."""
    log.spinner_start("Waiting for PostgreSQL…")
    elapsed = 0
    while elapsed < timeout:
        try:
            result = subprocess.run(
                [
                    "docker",
                    "exec",
                    container_name("postgres"),
                    "pg_isready",
                    "-U",
                    "minder",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            ready = result.returncode == 0
        except OSError:
            ready = False
        if ready:
            log.spinner_stop()
            log.success("PostgreSQL is ready")
            return True
        time.sleep(2)
        elapsed += 2
    log.spinner_stop()
    log.error(f"PostgreSQL did not become ready within {timeout}s")
    return False


def compose(*args: object) -> int:
    return run("docker", "compose", "-f", config.COMPOSE_FILE, *args)


def compose_monitoring(*args: object) -> int:
    return run(
        "docker", "compose", "-f", config.COMPOSE_FILE, "--profile", "monitoring", *args
    )
