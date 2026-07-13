"""Configuration constants — ported from scripts/lib/config.sh (#7, Stage 2).

The Python side's single source of truth for paths, names, and flags. Grows
incrementally as verbs are ported (strangler-fig): only what a ported module
actually consumes lives here yet. The bash `config.sh` stays authoritative for
the still-bash modules; these values are kept identical to it.
"""

import os
import sys
from pathlib import Path

# bash SCRIPT_DIR = the setup.sh dir = repo root (this file is scripts/setup/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT

# Mirrors setup.sh:30-31.
SCRIPT_VERSION = "1.0.0"
SCRIPT_NAME = "setup.sh"

# Paths (config.sh PATHS block).
ENV_FILE = REPO_ROOT / ".env"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE_FILE = REPO_ROOT / "docker" / "compose" / "docker-compose.yml"
COMPOSE_ENV_FILE = REPO_ROOT / "docker" / "compose" / ".env"

# Tag cache (config.sh PATHS block). CACHE_TTL_HOURS: tag lists expire after 24h.
CACHE_DIR = REPO_ROOT / ".cache"
TAGS_CACHE_DIR = CACHE_DIR / "tags"
CACHE_TTL_HOURS = 24

# Wait/poll timeouts in seconds (config.sh TIMEOUTS block).
TIMEOUT_DB = 60
TIMEOUT_SERVICES = 90
TIMEOUT_MONITORING = 120
TIMEOUT_AI = 120
TIMEOUT_OLLAMA = 90
TIMEOUT_PORT = 30
TIMEOUT_REGISTRY = 8  # per registry HTTP call

# Service naming (config.sh SERVICE DEFINITIONS block).
CONTAINER_PREFIX = "minder"
NETWORK_NAME = "docker_minder-network"
MONITORING_NETWORK_NAME = "minder-monitoring"

# Service groups, in startup order (config.sh SERVICE DEFINITIONS block).
# ollama is intentionally absent — it is gated by the compose 'internal-ollama'
# profile, activated by start_services only in internal mode (see lifecycle.py).
SECURITY_SERVICES = ("traefik",)
CORE_SERVICES = ("postgres", "redis", "qdrant", "neo4j", "rabbitmq", "minio", "schema-registry")
API_SERVICES = (
    "api-gateway", "plugin-registry", "marketplace", "plugin-state-manager",
    "rag-pipeline", "model-management", "graph-rag",
)
AI_SERVICES = ("openwebui", "tts-stt")
MONITORING_SERVICES = (
    "influxdb", "telegraf", "prometheus", "grafana", "alertmanager", "jaeger", "otel-collector",
)
EXPORTER_SERVICES = (
    "postgres-exporter", "redis-exporter", "rabbitmq-exporter",
    "blackbox-exporter", "cadvisor", "node-exporter",
)

# Health endpoints "port[/path]" (config.sh SERVICE_PORTS). Only services with an
# entry are health-checked. Path defaults to /health when the value is bare port.
# (openwebui/rabbitmq are Traefik-only → intentionally absent; authelia disabled.)
SERVICE_PORTS = {
    "api-gateway": "8000/health",
    "plugin-registry": "8001/health",
    "marketplace": "8002/health",
    "plugin-state-manager": "8003/health",
    "rag-pipeline": "8004/health",
    "model-management": "8005/health",
    "tts-stt": "8006/health",
    "graph-rag": "8008/health",
    "prometheus": "9090/-/healthy",
    "grafana": "3000/api/health",
    "influxdb": "8086",
    "traefik": "8081/dashboard/",
    "minio": "9000/minio/health/live",
    "jaeger": "16686",
    "otel-collector": "18888/metrics",
}


def _truthy(val: str) -> bool:
    # bash run() accepts DRY_RUN in {1,true,yes} (case-insensitive).
    return (val or "").strip().lower() in ("1", "true", "yes")


# Flags. The env-var form is read here; __main__ also flips these when the
# equivalent global flag (--dry-run / --verbose) is present, mirroring setup.sh
# main()'s flag loop (DRY_RUN=true / VERBOSE=true).
DRY_RUN = _truthy(os.environ.get("DRY_RUN", ""))
VERBOSE = _truthy(os.environ.get("VERBOSE", ""))
# Smart version resolution off-switch (config.sh). check_prerequisites also flips
# this True when curl is unavailable.
SKIP_VERSION_CHECK = _truthy(os.environ.get("SKIP_VERSION_CHECK", ""))

# `stop --clean`/`--clean-dangling` sets this (config.sh: CLEAN_DANGLING=false
# default). __main__ flips it when the flag is present, mirroring setup.sh main().
CLEAN_DANGLING = _truthy(os.environ.get("CLEAN_DANGLING", ""))

# Interactive-prompt gate. config.sh: false if stdin is not a tty, OR CI="true",
# OR NONINTERACTIVE="true" (the CI/NONINTERACTIVE compares are exact, case-sensitive
# "true" — NOT the truthy set). Verbs use it to choose prompt-vs-error.
INTERACTIVE = (
    sys.stdin.isatty()
    and os.environ.get("CI", "false") != "true"
    and os.environ.get("NONINTERACTIVE", "false") != "true"
)
