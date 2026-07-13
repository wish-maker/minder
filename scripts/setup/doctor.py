"""`doctor` verb — ported from scripts/lib/commands.sh cmd_doctor (#7, Stage 2).

Deep diagnostics: Docker (version/compose/RAM), disk, .env (perms + weak-secret
scan), port availability, container health, dangling volumes, and image version
drift. Every reading is live/host-specific, so doctor_verify.sh compares
STRUCTURALLY (sections + labels + check set), masking the values + the issue count.
"""

import os
import re
import shutil
import socket
import subprocess

from . import config, log, versions

_PREFIX = config.CONTAINER_PREFIX + "-"
_DOCTOR_PORTS = (
    5432, 6379, 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8008,
    8080, 8081, 8086, 9090, 9091, 3000,
)
_WEAK_RE = re.compile(r"^(admin|password|secret|changeme|replace_me|minder)$")


def _bold(text: str) -> str:
    return f"{log._BOLD}{text}{log._NC}" if log._colors_on() else text


def _cap(argv: list) -> str:
    try:
        out = subprocess.run(argv, capture_output=True, text=True)
    except OSError:
        return ""
    return out.stdout


def _tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


def run() -> int:
    log.section("🩺  System Diagnostics")
    issues = 0

    # ── Docker ──
    log._emit(_bold("Docker"))
    log.detail(f"Version: {_cap(['docker', '--version']).strip()}")
    compose_v = _cap(["docker", "compose", "version", "--short"]).strip() or "n/a"
    log.detail(f"Compose: {compose_v}")
    mem_raw = _cap(["docker", "info", "--format", "{{.MemTotal}}"]).strip()
    try:
        mem_gb = int(mem_raw) // 1073741824
    except ValueError:
        mem_gb = 0
    if mem_gb < 4:
        log.warn(f"Docker has only {mem_gb}GB RAM (recommend ≥4GB for Ollama)")
        issues += 1
    else:
        log.detail(f"Docker RAM: {mem_gb}GB ✓")

    # ── Disk ──
    log._emit("\n" + _bold("Disk"))
    try:
        free_gb = shutil.disk_usage(str(config.SCRIPT_DIR)).free // 1073741824
    except OSError:
        free_gb = 999
    if free_gb < 10:
        log.warn(f"Low disk space: {free_gb}GB free")
        issues += 1
    else:
        log.detail(f"Free space: {free_gb}GB ✓")

    # ── Environment (.env) ──
    log._emit("\n" + _bold("Environment (.env)"))
    if not config.ENV_FILE.is_file():
        log.warn(".env not found — run install first")
        issues += 1
    else:
        try:
            perm = oct(os.stat(config.ENV_FILE).st_mode & 0o777)[2:]
        except OSError:
            perm = "???"
        if perm not in ("600", "0600"):
            log.warn(f".env permissions are {perm} — should be 600")
            issues += 1
        else:
            log.detail(f"Permissions: {perm} ✓")
        weak = 0
        try:
            lines = config.ENV_FILE.read_text(encoding="utf-8").splitlines()
        except OSError:
            lines = []
        for line in lines:
            key, sep, val = line.partition("=")
            if key.startswith("#"):
                continue
            if not sep or val == "":
                continue
            if _WEAK_RE.match(val):
                log.warn(f"Weak value detected for {key}")
                weak += 1
                issues += 1
        if weak == 0:
            log.detail("No obvious weak secrets ✓")

    # ── Port Availability ──
    log._emit("\n" + _bold("Port Availability"))
    ps_ports = _cap(["docker", "ps", "--format", "{{.Ports}}"])
    for port in _DOCTOR_PORTS:
        if _tcp_open(port):
            if f":{port}->" in ps_ports:
                log.detail(f":{port} — in use by Minder ✓")
            else:
                log.warn(f":{port} — in use by another process")
                issues += 1
        else:
            log.detail(f":{port} — free ✓")

    # ── Container Health ──
    log._emit("\n" + _bold("Container Health"))
    unhealthy = [
        n for n in _cap(["docker", "ps", "--filter", "health=unhealthy", "--format", "{{.Names}}"]).splitlines()
        if n.startswith(_PREFIX)
    ]
    if unhealthy:
        log.warn("Unhealthy containers:")
        for c in unhealthy:
            log.detail(f"  {c}")
        issues += 1
    else:
        running = sum(1 for n in _cap(["docker", "ps", "--format", "{{.Names}}"]).splitlines() if n.startswith(_PREFIX))
        log.detail(f"{running} containers running, none unhealthy ✓")

    # ── Docker Volumes ──
    log._emit("\n" + _bold("Docker Volumes"))
    dangling = len([v for v in _cap(["docker", "volume", "ls", "-q", "--filter", "dangling=true"]).splitlines() if v])
    if dangling > 5:
        log.warn(f"{dangling} dangling volumes (run: docker volume prune)")
    else:
        log.detail(f"Dangling volumes: {dangling} ✓")

    # ── Image Version Drift ──
    log._emit("\n" + _bold("Image Version Drift"))
    if config.SKIP_VERSION_CHECK:
        log.warn("Version check skipped (curl unavailable or SKIP_VERSION_CHECK=1)")
    else:
        log.info("Querying registries for newer compatible versions…")
        drift_count = versions.version_drift_report(False)
        if drift_count > 0:
            issues += 1

    log._emit("")
    if issues == 0:
        log.success("No issues found — system looks healthy 🎉")
    else:
        log.warn(f"{issues} issue(s) found — review warnings above")
    return 0
