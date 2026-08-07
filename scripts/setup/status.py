"""`status` verb — ported from scripts/lib/commands.sh cmd_status (#7, Stage 2).

`status --json` → run_health_checks(json). Human mode → a section header, a
container-count Summary, the `docker ps` container table, the `docker stats`
resource table, and the health report. The counts / statuses / CPU-mem-net
readings are live/non-deterministic, so status_verify.sh compares STRUCTURALLY
(container name set + headers + health structure), masking the varying values.

Operator extensions (#71, folded from the dropped scripts/health-check.sh — all
OPT-IN, so plain `status` is byte-identical and the gate stays green):
  --watch [secs]   live refresh loop (default 30s) until Ctrl+C
  --report [path]  write a timestamped health/resource/network snapshot to a file
  --fix            restart unhealthy/stopped minder containers, then show status
"""

import datetime
import subprocess
import sys
import time

from . import config, docker, env, health, log

_PREFIX = config.CONTAINER_PREFIX + "-"
_ROUTER = _PREFIX + "ollama-router"
_TTS_STT_ROUTER = _PREFIX + "tts-stt-router"


def _primary_reachable(hostport: str) -> bool:
    """True if the failover PRIMARY is reachable **from inside the router container** —
    probed there (busybox wget) rather than host-side so it reflects the router's
    actual network path (host and container can differ). Returns False if the router
    isn't running. Mirrors the bash `docker exec … wget` probe for the parity gate."""
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                _ROUTER,
                "wget",
                "-q",
                "-T",
                "3",
                "-O",
                "/dev/null",
                f"http://{hostport}/api/tags",
            ],
            capture_output=True,
        )
        return result.returncode == 0
    except OSError:
        return False


def _fallback_alive() -> bool:
    """#279: is the internal failover backup actually responsive — not just "the
    container exists in Running state" (it can be Up but hung), a live `ollama
    list` call, the same liveness probe health.download_ollama_models already
    uses. Checked regardless of whether the primary is currently reachable, so a
    dead backup doesn't stay invisible while the primary happens to be up —
    confirmed live (2026-08-04, the Pi): the backup container had silently died
    (OOM-suspected) and every health/status check kept reporting the platform as
    fully healthy the whole time, because the primary was still up."""
    if not docker.container_running("ollama"):
        return False
    return docker.cmd_ok(
        ["docker", "exec", docker.container_name("ollama"), "ollama", "list"]
    )


def _print_ollama_backend() -> None:
    """Show the active Ollama backend. In failover mode probe the primary so the user
    can see whether they are on the fast external primary or the internal fallback —
    otherwise a primary outage is only visible as unexplained slowness. (#21)"""
    primary = env.get("OLLAMA_FAILOVER_PRIMARY")
    base = env.get("OLLAMA_BASE_URL")
    log._emit(log.bold("Ollama Backend"))
    if primary:
        if _primary_reachable(primary):
            log._emit(
                f"  failover — primary {primary} REACHABLE "
                "→ serving from the external primary"
            )
        else:
            log._emit(
                f"  failover — primary {primary} UNREACHABLE "
                "→ serving from the internal fallback"
            )
        if not _fallback_alive():
            warn_icon = f"{log._YELLOW}⚠{log._NC}" if log._colors_on() else "⚠"
            log._emit(
                f"  {warn_icon} internal fallback container is not responding — "
                "no safety net if the primary goes down"
            )
    elif base:
        log._emit(f"  external — {base}")
    else:
        log._emit("  internal — platform-managed container")
    log._emit("")


def _tts_stt_primary_reachable(hostport: str) -> bool:
    """Same idea as _primary_reachable, probed from inside the tts-stt-router
    container against tts-stt's own /health endpoint (#65 item 4)."""
    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                _TTS_STT_ROUTER,
                "wget",
                "-q",
                "-T",
                "3",
                "-O",
                "/dev/null",
                f"http://{hostport}/health",
            ],
            capture_output=True,
        )
        return result.returncode == 0
    except OSError:
        return False


def _tts_stt_fallback_alive() -> bool:
    """Same idea as _fallback_alive — is the internal backup actually responsive,
    not just "container Running". No ollama-style CLI equivalent exists for
    tts-stt, so this probes its own /health endpoint directly instead."""
    if not docker.container_running("tts-stt"):
        return False
    return docker.cmd_ok(
        [
            "docker",
            "exec",
            docker.container_name("tts-stt"),
            "curl",
            "-sf",
            "http://localhost:8006/health",
        ]
    )


def _print_tts_stt_backend() -> None:
    """Show the active tts-stt backend — mirrors _print_ollama_backend exactly
    (#65 item 4, the second real external-binding case)."""
    primary = env.get("TTS_STT_FAILOVER_PRIMARY")
    base = env.get("TTS_STT_BASE_URL")
    log._emit(log.bold("tts-stt Backend"))
    if primary:
        if _tts_stt_primary_reachable(primary):
            log._emit(
                f"  failover — primary {primary} REACHABLE "
                "→ serving from the external primary"
            )
        else:
            log._emit(
                f"  failover — primary {primary} UNREACHABLE "
                "→ serving from the internal fallback"
            )
        if not _tts_stt_fallback_alive():
            warn_icon = f"{log._YELLOW}⚠{log._NC}" if log._colors_on() else "⚠"
            log._emit(
                f"  {warn_icon} internal fallback container is not responding — "
                "no safety net if the primary goes down"
            )
    elif base:
        log._emit(f"  external — {base}")
    else:
        log._emit("  internal — platform-managed container")
    log._emit("")


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


def _print_status() -> None:
    """The human status view: summary + container table + resource table + health."""
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

    log._emit(log.bold("Containers"))
    ps_table = _filtered(
        ["docker", "ps", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        "NAMES",
    )[:30]
    for ln in ps_table:
        log._emit(ln)
    log._emit("")

    log._emit(log.bold("Resource Usage"))
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

    _print_ollama_backend()
    _print_tts_stt_backend()

    health.run_health_checks()


def _unhealthy_or_stopped() -> "list[str]":
    """minder- containers that are unhealthy OR exited/created (candidates for --fix)."""
    names: "list[str]" = []
    seen: "set[str]" = set()
    specs = [
        ["docker", "ps", "--filter", "health=unhealthy", "--format", "{{.Names}}"],
        ["docker", "ps", "-a", "--filter", "status=exited", "--format", "{{.Names}}"],
        ["docker", "ps", "-a", "--filter", "status=created", "--format", "{{.Names}}"],
    ]
    for argv in specs:
        try:
            out = subprocess.run(argv, capture_output=True, text=True).stdout
        except OSError:
            continue
        for ln in out.splitlines():
            if ln.startswith(_PREFIX) and ln not in seen:
                seen.add(ln)
                names.append(ln)
    return names


def _fix_unhealthy() -> None:
    """--fix: restart unhealthy/stopped minder containers (opt-in operator action)."""
    log.section("🔧  Fix — restart unhealthy/stopped containers")
    targets = _unhealthy_or_stopped()
    if not targets:
        log.success("No unhealthy or stopped containers — nothing to fix")
        return
    log.warn(f"Restarting {len(targets)} container(s): {', '.join(targets)}")
    for name in targets:
        if docker.run("docker", "restart", name) == 0:
            log.success(f"restarted {name}")
        else:
            log.warn(f"failed to restart {name}")


def _write_report(report_path: str) -> int:
    """--report: write a timestamped health/resource/network snapshot to a file."""
    now = datetime.datetime.now()
    ts = now.strftime("%Y%m%d-%H%M%S")
    if report_path:
        out_path = report_path
    else:
        config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = str(config.LOGS_DIR / f"health-report-{ts}.txt")

    lines = [
        f"Minder health report — {now.isoformat()}",
        "=" * 60,
        "",
        "[Summary]",
        f"  total={_count([])}  healthy={_count(['--filter', 'health=healthy'])}  "
        f"starting={_count(['--filter', 'health=starting'])}  "
        f"unhealthy={_count(['--filter', 'health=unhealthy'])}",
        "",
        "[Containers]  (Status column carries health)",
    ]
    lines += _filtered(
        ["docker", "ps", "-a", "--format", "table {{.Names}}\t{{.Status}}\t{{.Ports}}"],
        "NAMES",
    )
    lines += ["", "[Resource Usage]"]
    lines += _filtered(
        [
            "docker",
            "stats",
            "--no-stream",
            "--format",
            "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}",
        ],
        "NAME",
    )
    lines += ["", "[Network]"]
    lines += (docker.capture(["docker", "network", "ls"]) or "").splitlines()

    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
    except OSError as e:
        log.error(f"Failed to write report to {out_path}: {e}")
        return 1
    log.success(f"Health report written → {out_path}")
    return 0


def _watch(interval: int) -> int:
    """--watch: re-render the status view every `interval` seconds until Ctrl+C."""
    try:
        while True:
            if log._colors_on():
                sys.stdout.write("\033[2J\033[H")  # clear screen + home
                sys.stdout.flush()
            _print_status()
            log.detail(f"↻ refreshing every {interval}s — Ctrl+C to stop")
            time.sleep(interval)
    except KeyboardInterrupt:
        log._emit("")
        return 0


def run(
    json_mode: bool = False,
    *,
    watch: int = 0,
    report: bool = False,
    report_path: str = "",
    fix: bool = False,
) -> int:
    if json_mode:
        health.run_health_checks(json_mode=True)
        return 0
    if fix:
        _fix_unhealthy()
        log._emit("")
    if report:
        return _write_report(report_path)
    if watch:
        return _watch(watch)
    _print_status()
    return 0
