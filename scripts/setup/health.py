"""Health checks — ported from scripts/lib/health.sh (#7, Stage 2).

`run_health_checks(json_mode)` probes each SERVICE_PORTS endpoint (HTTP via
urllib, or a TCP check for influxdb) and prints a grouped human report or a JSON
summary. The up/down results + server IP + counts are LIVE/non-deterministic, so
they are value-masked exactly like the gate's normalize.sed — what's verified is
the STRUCTURE (which services, in which groups, in order). curl is replaced by
urllib (cross-platform); reachability is what matters and it's masked anyway.

Also here: download_ollama_models (spinner + `ollama pull` — network + mutating,
entered only from cmd_install).
"""

import os
import socket
import time
import urllib.request
from datetime import datetime, timezone

from . import config, docker, env, log


def _server_ip() -> str:
    # bash: hostname -I|awk (Linux) → hostname -i → hostname → localhost. Best-effort
    # cross-platform equivalent; the value is display-only and masked in the gate.
    try:
        ip = socket.gethostbyname(socket.gethostname())
    except OSError:
        ip = ""
    return ip or "localhost"


def _http_ok(url: str) -> bool:
    # bash: curl -sf --max-time 3 (fails on HTTP >= 400). urllib stand-in.
    try:
        with urllib.request.urlopen(
            url, timeout=3
        ) as resp:  # noqa: S310 (local health URL)
            return 200 <= resp.status < 300
    except Exception:
        return False


def run_health_checks(json_mode: bool = False) -> int:
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
            if docker.tcp_open("127.0.0.1", port):
                results.append((name, "ok", display_url))
                if not json_mode:
                    if log._colors_on():
                        log._emit(
                            f"  {log._GREEN}✓{log._NC} {name}  {log._DIM}{display_url}{log._NC}  {log._DIM}(TCP port check){log._NC}"  # noqa: E501
                        )
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
                    log._emit(
                        f"  {log._GREEN}✓{log._NC} {name}  {log._DIM}{display_url}{log._NC}"
                    )
                else:
                    log._emit(f"  ✓ {name}  {display_url}")
        else:
            results.append((name, "warn", display_url))
            if not json_mode:
                _warn_line(name, display_url)

    def _warn_line(name: str, url: str) -> None:
        if log._colors_on():
            log._emit(
                f"  {log._YELLOW}⚠{log._NC} {name}  {log._DIM}{url}  (not yet reachable){log._NC}"
            )
        else:
            log._emit(f"  ⚠ {name}  {url}  (not yet reachable)")

    if not json_mode:
        log.section("🔍  Health Check")
        log._emit(log.bold("Core APIs"))
    for svc in config.API_SERVICES:
        if svc in config.SERVICE_PORTS:
            _check_endpoint(svc, config.SERVICE_PORTS[svc])

    if not json_mode:
        log._emit("\n" + log.bold("Monitoring"))
    for svc in ("prometheus", "grafana", "influxdb", "traefik", "rabbitmq"):
        if svc in config.SERVICE_PORTS:
            _check_endpoint(svc, config.SERVICE_PORTS[svc])

    if not json_mode:
        log._emit("\n" + log.bold("AI Services"))
    # NOTE: the service key is "tts-stt" (SERVICE_PORTS + AI_SERVICES); the bash
    # original looped "tts-stt-service" (a stale name) so it never matched → tts-stt
    # was silently never health-checked. Fixed here + in the bash reference.
    for svc in ("openwebui", "tts-stt"):
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
        return warn_count

    log._emit("")
    if warn_count == 0:
        log.success(f"{ok_count}/{len(results)} endpoints healthy 🎉")
    else:
        log.warn(
            f"{ok_count}/{len(results)} endpoints reachable — {warn_count} still starting"
        )
        log.detail(f"Re-check: ./{config.SCRIPT_NAME} status")
    return warn_count


def download_ollama_models() -> None:
    """bash download_ollama_models: in internal mode, wait for the platform ollama
    container, then pull each OLLAMA_MODELS entry (dry-run-gated). External mode
    (OLLAMA_BASE_URL set) skips — the external host owns its models."""
    log.section("🤖  AI Model Download")

    ollama_url = os.environ.get("OLLAMA_BASE_URL") or env.get("OLLAMA_BASE_URL")
    if ollama_url:
        log.info(
            "🌐 External Ollama mode (OLLAMA_BASE_URL set) — skipping in-container model pull"
        )
        log.detail(
            "Pull models on the external host, e.g.:  ollama pull llama3.2 && ollama pull nomic-embed-text"
        )
        return

    ollama = docker.container_name("ollama")
    log.spinner_start("Waiting for Ollama daemon…")
    elapsed = 0
    ready = False
    while elapsed < config.TIMEOUT_OLLAMA:
        if docker.cmd_ok(["docker", "exec", ollama, "ollama", "list"]):
            log.spinner_stop()
            log.success("Ollama is ready")
            ready = True
            break
        time.sleep(3)
        elapsed += 3
    if not ready:
        log.spinner_stop()
        log.warn(
            f"Ollama did not start within {config.TIMEOUT_OLLAMA}s — skipping model pull"
        )
        log.detail(f"Pull later:  docker exec {ollama} ollama pull <model>")
        return

    if (env.get("OLLAMA_AUTOMATIC_PULL") or "true") != "true":
        log.info("OLLAMA_AUTOMATIC_PULL=false — skipping")
        return

    model_list = env.get("OLLAMA_MODELS") or "llama3.2,nomic-embed-text"
    models = model_list.split(",")
    # bash: log_info "Pulling N model(s): ${models[*]}" — with IFS=$'\n\t' the array
    # joins on a NEWLINE (IFS's first char), so the names land on separate lines.
    log.info(f"Pulling {len(models)} model(s): {chr(10).join(models)}")
    for model in models:
        model = model.strip()  # xargs trim
        if not model:
            continue
        log.spinner_start(f"Pulling {model}…")
        # bash: run timeout 300 docker exec … ollama pull … &>/dev/null → quiet.
        if (
            docker.run(
                "timeout",
                "300",
                "docker",
                "exec",
                ollama,
                "ollama",
                "pull",
                model,
                quiet=True,
            )
            == 0
        ):
            log.spinner_stop()
            log.success(model)
        else:
            log.spinner_stop()
            log.warn(f"{model} — failed or timed out")

    # `ollama list | tail -n +2` — skip the header row; the rest is live/non-det.
    listing = docker.capture(["docker", "exec", ollama, "ollama", "list"]).splitlines()[
        1:
    ]
    log.success(f"{len(listing)} model(s) available")
    for line in listing:
        log.detail(line)
