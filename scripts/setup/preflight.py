"""Preflight validation — ported from scripts/lib/preflight.sh (#7, Stage 2).

Ports the two PURE, deterministic Phase-4 config validators — they read a mode
from `.env` (via env.get), print the resolved configuration, and export the
derived vars that docker compose consumes:

    validate_ai_compute_mode · validate_compute_resource_profile

Deferred (environment-dependent or mutating, and only entered from the still-bash
start/install verbs): check_prerequisites (docker/disk/port probes),
validate_gpu_environment (`docker run --gpus`), and validate_access_mode /
configure_traefik_access_mode (which MOVES traefik dynamic config files).
"""

import os

from . import env, log


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
