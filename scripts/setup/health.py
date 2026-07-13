"""Health checks — ported from scripts/lib/health.sh (#7, Stage 2).

`run_health_checks(json_mode)` probes each SERVICE_PORTS endpoint (HTTP via
urllib, or a TCP check for influxdb) and prints a grouped human report or a JSON
summary. The up/down results + server IP + counts are LIVE/non-deterministic, so
they are value-masked exactly like the gate's normalize.sed — what's verified is
the STRUCTURE (which services, in which groups, in order). curl is replaced by
urllib (cross-platform); reachability is what matters and it's masked anyway.

Deferred: download_ollama_models (spinner + `ollama pull` — network + mutating,
entered only from cmd_install).
"""

import socket
import urllib.request
from datetime import datetime, timezone

from . import config, docker, log


def _server_ip() -> str:
    # bash: hostname -I|awk (Linux) → hostname -i → hostname → localhost. Best-effort
    # cross-platform equivalent; the value is display-only and masked in the gate.
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = ""
    return ip or "localhost"


def _tcp_open(host: str, port: str) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=2):
            return True
    except OSError:
        return False


def _http_ok(url: str) -> bool:
    # bash: curl -sf --max-time 3 (fails on HTTP >= 400). urllib stand-in.
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:  # noqa: S310 (local health URL)
            return 200 <= resp.status < 300
    except Exception:
        return False


def _bold(text: str) -> str:
    return f"{log._BOLD}{text}{log._NC}" if log._colors_on() else text


def run_health_checks(json_mode: bool = False) -> None:
    results: "list[tuple[str, str, str]]" = []  # (name, status, url-or-msg)
    server_ip = _server_ip()

    def _check_endpoint(name: str, path: str) -> None:
        port = path.split("/", 1)[0]
        health_path = path.split("/", 1)[1] if "/" in path else path
        if health_path == port:  # bare "port" spec → default health path
            health_path = "/health"

        if not docker.container_running(name):
            results.append((name, "error", "container not running"))
            if not json_mode:
                if log._colors_on():
                    log._emit(f"  {log._RED}✗{log._NC} {name}  (container not running)")
                else:
                    log._emit(f"  ✗ {name}  (container not running)")
            return

        if not health_path.startswith("/"):
            health_path = "/" + health_path
        display_url = f"http://{server_ip}:{port}{health_path}"

        # InfluxDB v3 needs auth for HTTP endpoints → a plain TCP port check.
        if name == "influxdb":
            if _tcp_open("127.0.0.1", port):
                results.append((name, "ok", display_url))
                if not json_mode:
                    if log._colors_on():
                        log._emit(f"  {log._GREEN}✓{log._NC} {name}  {log._DIM}{display_url}{log._NC}  {log._DIM}(TCP port check){log._NC}")
                    else:
                        log._emit(f"  ✓ {name}  {display_url}  (TCP port check)")
            else:
                results.append((name, "warn", display_url))
                if not json_mode:
                    _warn_line(name, display_url)
            return

        if _http_ok(display_url):
            results.append((name, "ok", display_url))
            if not json_mode:
                if log._colors_on():
                    log._emit(f"  {log._GREEN}✓{log._NC} {name}  {log._DIM}{display_url}{log._NC}")
                else:
                    log._emit(f"  ✓ {name}  {display_url}")
        else:
            results.append((name, "warn", display_url))
            if not json_mode:
                _warn_line(name, display_url)

    def _warn_line(name: str, url: str) -> None:
        if log._colors_on():
            log._emit(f"  {log._YELLOW}⚠{log._NC} {name}  {log._DIM}{url}  (not yet reachable){log._NC}")
        else:
            log._emit(f"  ⚠ {name}  {url}  (not yet reachable)")

    if not json_mode:
        log.section("🔍  Health Check")
        log._emit(_bold("Core APIs"))
    for svc in config.API_SERVICES:
        if svc in config.SERVICE_PORTS:
            _check_endpoint(svc, config.SERVICE_PORTS[svc])

    if not json_mode:
        log._emit("\n" + _bold("Monitoring"))
    for svc in ("prometheus", "grafana", "influxdb", "traefik", "rabbitmq"):
        if svc in config.SERVICE_PORTS:
            _check_endpoint(svc, config.SERVICE_PORTS[svc])

    if not json_mode:
        log._emit("\n" + _bold("AI Services"))
    for svc in ("openwebui", "tts-stt-service"):
        if svc in config.SERVICE_PORTS:
            _check_endpoint(svc, config.SERVICE_PORTS[svc])

    ok_count = sum(1 for _, s, _ in results if s == "ok")
    warn_count = sum(1 for _, s, _ in results if s == "warn")

    if json_mode:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        log._emit("{")
        log._emit(f'  "timestamp": "{ts}",')
        log._emit(f'  "ok": {ok_count},')
        log._emit(f'  "warn": {warn_count},')
        log._emit('  "services": [')
        n = len(results)
        for i, (name, status, url) in enumerate(results):
            sep = "," if i < n - 1 else ""
            log._emit(f'    {{"name":"{name}","status":"{status}","url":"{url}"}}{sep}')
        log._emit("  ]")
        log._emit("}")
        return

    log._emit("")
    if warn_count == 0:
        log.success(f"{ok_count}/{len(results)} endpoints healthy 🎉")
    else:
        log.warn(f"{ok_count}/{len(results)} endpoints reachable — {warn_count} still starting")
        log.detail(f"Re-check: ./{config.SCRIPT_NAME} status")
