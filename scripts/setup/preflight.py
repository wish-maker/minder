"""Preflight validation — ported from scripts/lib/preflight.sh (#7, Stage 2).

The prerequisite + Phase-4 validation steps the install/start verbs run first:
  check_prerequisites            docker/compose/daemon + openssl/curl + disk + ports
  validate_gpu_environment       NVIDIA Container Toolkit probe → GPU_AVAILABLE
  validate_access_mode           local/vpn/public → TRAEFIK_ACCESS_MODE + dynamic cfg
  configure_traefik_access_mode  enable the matching access-mode-<mode>.yml
  validate_ai_compute_mode       internal/external/hybrid → AI_* env
  validate_compute_resource_profile  low/medium/high/enterprise → CPU/MEM limits

The validators read a mode from `.env` (via env.get), print the resolved
configuration, and export the derived vars that docker compose consumes.
"""

import os
import shutil
import socket
import subprocess

from . import config, env, log

# Host ports check_prerequisites probes for conflicts (config.sh order).
_PREREQ_PORTS = (
    5432,
    6379,
    8000,
    8001,
    8002,
    8003,
    8004,
    8005,
    8006,
    8008,
    8080,
    8081,
    8086,
    9090,
    9091,
    3000,
)


def _cmd_ok(argv: list) -> bool:
    """True if the command runs and exits 0 (bash `cmd &>/dev/null`)."""
    try:
        return (
            subprocess.run(
                argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode
            == 0
        )
    except OSError:
        return False


def _capture(argv: list) -> str:
    try:
        out = subprocess.run(argv, capture_output=True, text=True)
    except OSError:
        return ""
    return out.stdout if out.returncode == 0 else ""


def _free_gb(path: object) -> int:
    """Free space in GiB (bash `df -BG … | awk NR==2 $4`); 999 if unknown."""
    try:
        return shutil.disk_usage(str(path)).free // 1073741824
    except OSError:
        return 999


def _busy_ports() -> list:
    """Ports open on 127.0.0.1 that are NOT published by a minder container
    (bash: >/dev/tcp probe + `docker ps --format {{.Ports}}` grep ":port->")."""
    try:
        ps_ports = subprocess.run(
            ["docker", "ps", "--format", "{{.Ports}}"], capture_output=True, text=True
        ).stdout
    except OSError:
        ps_ports = ""
    busy = []
    for port in _PREREQ_PORTS:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                open_ = True
        except OSError:
            open_ = False
        if open_ and f":{port}->" not in ps_ports:
            busy.append(str(port))
    return busy


def check_prerequisites() -> None:
    """bash check_prerequisites: docker/compose/daemon + openssl/curl + compose
    file + disk + port conflicts. Exits 1 if a hard requirement is missing."""
    log.step("Checking prerequisites")
    failed = False

    if shutil.which("docker") is None:
        log.error("Docker not installed → https://docs.docker.com/get-docker/")
        failed = True
    else:
        # docker --version | awk '{print $3}' | tr -d ','
        parts = _capture(["docker", "--version"]).split()
        version = parts[2].rstrip(",") if len(parts) > 2 else ""
        log.detail(f"Docker {version}")

    if not _cmd_ok(["docker", "compose", "version"]):
        log.error(
            "Docker Compose v2 not available → https://docs.docker.com/compose/install/"
        )
        failed = True
    else:
        cver = _capture(["docker", "compose", "version", "--short"]).strip() or "v2"
        log.detail(f"Compose {cver}")

    if not _cmd_ok(["docker", "info"]):
        log.error("Docker daemon is not running — start Docker Desktop or dockerd")
        failed = True

    if shutil.which("openssl") is None:
        log.warn(
            "openssl not found — falling back to /dev/urandom for secret generation"
        )

    if shutil.which("curl") is None:
        log.warn("curl not found — smart version resolution will be skipped")
        config.SKIP_VERSION_CHECK = True

    if not config.COMPOSE_FILE.is_file():
        log.error(f"Compose file not found: {config.COMPOSE_FILE}")
        failed = True
    else:
        log.detail(f"Compose file: {config.COMPOSE_FILE}")

    free_gb = _free_gb(config.SCRIPT_DIR)
    if free_gb < 10:
        log.warn(f"Low disk space: {free_gb}GB free (recommend ≥10GB)")
    else:
        log.detail(f"Disk space: {free_gb}GB free")

    busy = _busy_ports()
    if busy:
        log.warn(f"Ports already in use (may conflict): {' '.join(busy)}")

    if failed:
        log.error("Prerequisites failed — cannot continue")
        raise SystemExit(1)

    log.success("All prerequisites satisfied")


def validate_gpu_environment() -> None:
    """bash validate_gpu_environment: probe the NVIDIA Container Toolkit via a
    throwaway `docker run --gpus`; on failure (or no GPU) fall back to CPU and set
    GPU_AVAILABLE=false, else record the detected GPU and set GPU_AVAILABLE=true."""
    log.info("Validating GPU environment for AI acceleration...")

    if not _cmd_ok(
        [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "nvidia/cuda:11.0-base-ubuntu20.04",
            "nvidia-smi",
        ]
    ):
        log.warn("NVIDIA Container Toolkit not found")
        log.detail("GPU acceleration disabled - falling back to CPU mode")
        log.detail(
            "Install: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide"
        )
        os.environ["GPU_AVAILABLE"] = "false"
        return

    gpu_count = (
        _capture(["nvidia-smi", "--query-gpu=count", "--format=csv,noheader"]).strip()
        or "0"
    )
    try:
        count_zero = int(gpu_count) == 0
    except ValueError:
        count_zero = False
    if count_zero:
        log.warn("No NVIDIA GPUs detected - falling back to CPU mode")
        os.environ["GPU_AVAILABLE"] = "false"
        return

    log.detail(f"GPUs detected: {gpu_count}")
    gpu_model = (
        _capture(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"]
        ).splitlines()
        or ["Unknown"]
    )[0]
    log.detail(f"GPU Model: {gpu_model}")
    gpu_memory = (
        _capture(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader"]
        ).splitlines()
        or ["Unknown"]
    )[0]
    log.detail(f"GPU Memory: {gpu_memory}")
    os.environ["GPU_AVAILABLE"] = "true"
    log.success("GPU validation passed - hardware acceleration enabled")


def configure_traefik_access_mode() -> None:
    """bash configure_traefik_access_mode: disable every access-mode-*.yml, then
    enable access-mode-<mode>.yml (by renaming its .disabled twin)."""
    mode = env.get("ACCESS_MODE") or "local"
    log.info(f"Configuring Traefik access mode: {mode}")

    dyn = config.SCRIPT_DIR / "docker" / "services" / "traefik" / "dynamic"
    for cfg in sorted(dyn.glob("access-mode-*.yml")):
        cfg.rename(cfg.parent / (cfg.name + ".disabled"))

    target = dyn / f"access-mode-{mode}.yml.disabled"
    if target.is_file():
        target.rename(target.parent / target.name[: -len(".disabled")])
        log.success(f"Enabled Traefik config: access-mode-{mode}.yml")
    else:
        log.warn(f"Traefik config not found: access-mode-{mode}.yml")
        log.detail("Using default middleware configuration")


def validate_access_mode() -> int:
    """bash validate_access_mode: local (localhost) / vpn (LAN+VPN) / public
    (internet) — log the posture, export TRAEFIK_ACCESS_MODE, then wire the
    matching Traefik dynamic config."""
    mode = env.get("ACCESS_MODE") or "local"
    log.info("Validating Access Mode configuration...")

    if mode == "local":
        log.detail("Access Mode: LOCAL (localhost only)")
        log.detail("Services accessible only on 127.0.0.1")
        os.environ["TRAEFIK_ACCESS_MODE"] = "local"
    elif mode == "vpn":
        log.detail("Access Mode: VPN (LAN/VPN subnets)")
        log.detail("Services accessible via VPN with enhanced security")
        log.detail("Allowed CIDRs: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16")
        os.environ["TRAEFIK_ACCESS_MODE"] = "vpn"
    elif mode == "public":
        log.detail("Access Mode: PUBLIC (internet-facing)")
        log.detail("Services accessible via internet with DDoS protection")
        log.detail("WARNING: Ensure SSL certificates and firewall rules are configured")
        os.environ["TRAEFIK_ACCESS_MODE"] = "public"
    else:
        log.error(f"Invalid ACCESS_MODE: {mode}")
        log.detail("Valid options: local, vpn, public")
        log.detail(f"Fix: Set ACCESS_MODE in {env.ENV_FILE}")
        return 1

    configure_traefik_access_mode()
    log.success(f"Access Mode validation passed: {mode}")
    return 0


def validate_ai_compute_mode() -> int:
    """bash validate_ai_compute_mode: internal (local Ollama) / external (remote
    GPU node, requires EXTERNAL_GPU_NODE_URL) / hybrid (local + fallback)."""
    mode = env.get("AI_COMPUTE_MODE") or "internal"

    log.info("Validating AI Compute Mode configuration...")

    if mode == "internal":
        log.detail("AI Compute Mode: INTERNAL (local Ollama)")
        log.detail("Using local Docker Ollama service: minder-ollama:11434")
        os.environ["AI_ENDPOINT_STRATEGY"] = "local"
        os.environ["AI_LOCAL_OLLAMA_URL"] = "http://minder-ollama:11434"
        os.environ["AI_ENABLE_FALLBACK"] = "false"
    elif mode == "external":
        external_url = env.get("EXTERNAL_GPU_NODE_URL")
        if not external_url:
            log.error("AI_COMPUTE_MODE=external requires EXTERNAL_GPU_NODE_URL")
            log.detail(f"Fix: Set EXTERNAL_GPU_NODE_URL in {env.ENV_FILE}")
            log.detail("Example: http://gpu-node.example.com:11434")
            return 1
        log.detail("AI Compute Mode: EXTERNAL (remote GPU node)")
        log.detail(f"Routing AI requests to: {external_url}")
        os.environ["AI_ENDPOINT_STRATEGY"] = "external"
        os.environ["AI_LAN_OLLAMA_URL"] = external_url
        os.environ["AI_ENABLE_FALLBACK"] = "false"
    elif mode == "hybrid":
        external_url = env.get("EXTERNAL_GPU_NODE_URL")
        if not external_url:
            log.warn("AI_COMPUTE_MODE=hybrid recommended EXTERNAL_GPU_NODE_URL")
            log.detail("Proceeding with local-only mode (no external fallback)")
            external_url = "http://minder-ollama:11434"
        log.detail("AI Compute Mode: HYBRID (local + external fallback)")
        log.detail("Primary: local Ollama (minder-ollama:11434)")
        log.detail(f"Fallback: {external_url}")
        os.environ["AI_ENDPOINT_STRATEGY"] = "hybrid"
        os.environ["AI_LOCAL_OLLAMA_URL"] = "http://minder-ollama:11434"
        os.environ["AI_LAN_OLLAMA_URL"] = external_url
        os.environ["AI_ENABLE_FALLBACK"] = "true"
        os.environ["AI_FALLBACK_TIMEOUT_MS"] = "5000"
    else:
        log.error(f"Invalid AI_COMPUTE_MODE: {mode}")
        log.detail("Valid options: internal, external, hybrid")
        log.detail(f"Fix: Set AI_COMPUTE_MODE in {env.ENV_FILE}")
        return 1

    log.success(f"AI Compute Mode validation passed: {mode}")
    return 0


def validate_compute_resource_profile() -> int:
    """bash validate_compute_resource_profile: low / medium / high / enterprise —
    sets CPU/memory limits; enterprise notes GPU status from GPU_AVAILABLE."""
    profile = env.get("COMPUTE_RESOURCE_PROFILE") or "medium"

    log.info("Validating Compute Resource Profile...")

    if profile == "low":
        log.detail("Resource Profile: LOW (development)")
        log.detail("CPU limits: 1 core, Memory: 2GB per service")
        os.environ["COMPUTE_CPU_LIMIT"] = "1.0"
        os.environ["COMPUTE_MEMORY_LIMIT"] = "2g"
    elif profile == "medium":
        log.detail("Resource Profile: MEDIUM (staging)")
        log.detail("CPU limits: 2 cores, Memory: 4GB per service")
        os.environ["COMPUTE_CPU_LIMIT"] = "2.0"
        os.environ["COMPUTE_MEMORY_LIMIT"] = "4g"
    elif profile == "high":
        log.detail("Resource Profile: HIGH (production)")
        log.detail("CPU limits: 4 cores, Memory: 8GB per service")
        os.environ["COMPUTE_CPU_LIMIT"] = "4.0"
        os.environ["COMPUTE_MEMORY_LIMIT"] = "8g"
    elif profile == "enterprise":
        log.detail("Resource Profile: ENTERPRISE (GPU-accelerated)")
        log.detail("CPU limits: 8 cores, Memory: 16GB per service + GPU passthrough")
        os.environ["COMPUTE_CPU_LIMIT"] = "8.0"
        os.environ["COMPUTE_MEMORY_LIMIT"] = "16g"
        if os.environ.get("GPU_AVAILABLE") == "true":
            log.detail("GPU acceleration: ENABLED")
        else:
            log.warn("GPU acceleration: DISABLED (no NVIDIA GPU detected)")
    else:
        log.error(f"Invalid COMPUTE_RESOURCE_PROFILE: {profile}")
        log.detail("Valid options: low, medium, high, enterprise")
        return 1

    log.success(f"Resource Profile validation passed: {profile}")
    return 0
