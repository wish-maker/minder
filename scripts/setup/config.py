"""Configuration constants — ported from scripts/lib/config.sh (#7, Stage 2).

The Python side's single source of truth for paths, names, and flags — the
counterpart to scripts/lib/config.sh, kept identical to it (config.sh is now the
frozen behavior-gate reference).
"""

import datetime
import os
import sys
from pathlib import Path

# bash SCRIPT_DIR = the setup.sh dir = repo root (this file is scripts/setup/config.py).
REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = REPO_ROOT
# NOTE: `src/` is put on sys.path in scripts/setup/__init__.py (runs before any
# submodule) so setup modules can import the shared bundle brain (#65).

# Mirrors setup.sh:30-31.
SCRIPT_VERSION = "1.0.0"
SCRIPT_NAME = "setup.sh"

# Paths (config.sh PATHS block).
ENV_FILE = REPO_ROOT / ".env"
# Audit log path (config.sh: LOGS_DIR / setup-<ts>.log, stamped once at load). The
# logs/*.log file mirroring itself is deferred; the path is referenced by the
# success banner + log epilogue.
LOGS_DIR = REPO_ROOT / "logs"
LOG_FILE = LOGS_DIR / f"setup-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}.log"
BACKUP_DIR = REPO_ROOT / "backups"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"
COMPOSE_ENV_FILE = REPO_ROOT / "docker" / ".env"
# Bundle enable-state — a dedicated, SECRET-FREE JSON file (unlike .env, which
# carries DB passwords/JWT). Kept separate precisely so the network-facing
# plugin-registry can safely mount just this when the API lands. Absent file/key →
# enabled, so the default start path + setup gate stay byte-identical. See
# docs/architecture/bundles.md.
BUNDLES_STATE = REPO_ROOT / "bundles.state.json"
# telegraf.conf: the tracked TEMPLATE is the seed; the gitignored RUNTIME copy is
# what both containers mount, so the telegraf plugin writes its managed region to
# the runtime file and never dirties the repo. Mirrors ENV_EXAMPLE→COMPOSE_ENV_FILE.
TELEGRAF_TEMPLATE = REPO_ROOT / "docker" / "services" / "telegraf" / "telegraf.conf"
TELEGRAF_RUNTIME = (
    REPO_ROOT / "docker" / "services" / "telegraf" / "telegraf.runtime.conf"
)

# Module plugins — the claim graph's second source (#65 item 5): a plugin MAY ship
# src/plugins/<name>/manifest.yml declaring its own bundle/claims/binding metadata.
# No plugin does today (see bundle_graph.py's module docstring on that section) —
# this is just where bundles.py looks for one, if it ever exists.
PLUGINS_DIR = REPO_ROOT / "src" / "plugins"

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
NETWORK_NAME = "minder-network"  # #274: dropped the stale "docker_" prefix
MONITORING_NETWORK_NAME = "minder-monitoring"

# Service groups, in startup order (config.sh SERVICE DEFINITIONS block).
# ollama is intentionally absent — it is gated by the compose 'internal-ollama'
# profile, activated by start_services only in internal mode (see lifecycle.py).
SECURITY_SERVICES = ("traefik", "authelia")
CORE_SERVICES = (
    "postgres",
    "redis",
    "qdrant",
    "neo4j",
    "rabbitmq",
    "minio",
    "schema-registry",
)
API_SERVICES = (
    "api-gateway",
    "plugin-registry",
    "marketplace",
    "plugin-state-manager",
    "rag-pipeline",
    "model-management",
    "graph-rag",
)
AI_SERVICES = ("openwebui", "tts-stt")
MONITORING_SERVICES = (
    "influxdb",
    "telegraf",
    "prometheus",
    "grafana",
    "alertmanager",
    "jaeger",
    "otel-collector",
)
EXPORTER_SERVICES = (
    "postgres-exporter",
    "redis-exporter",
    "rabbitmq-exporter",
    "blackbox-exporter",
    "cadvisor",
    "node-exporter",
)

# Auxiliary databases created by initialize_database (infra.sh EXTRA_DATABASES).
# #294: minder_authelia/minder_schemaregistry were missing here — both are
# hardcoded, non-configurable database names (services/authelia/
# configuration.yml's `database: minder_authelia`; docker-compose.yml's
# schema-registry QUARKUS_DATASOURCE_JDBC_URL/REGISTRY_DATASOURCE_URL), so on
# a fresh install both containers fatally crashed on every single startup
# ("database ... does not exist") and were restarted by Docker's on-failure
# policy forever (confirmed live on the Pi: 835 and 363 restarts respectively).
EXTRA_DATABASES = (
    "minder_marketplace",
    "minder_authelia",
    "minder_schemaregistry",
    "tefas_db",
    "weather_db",
    "news_db",
    "crypto_db",
)

# Per-image version-resolution metadata "stable_prefix|constraint" (config.sh
# THIRD_PARTY_IMAGE_META). The pinned VERSION lives only in docker-compose.yml;
# versions.third_party_image_specs() joins each 3rd-party compose image with this.
# (authelia is enabled + core now (#15) but stays pinned in compose — not yet
# smart-resolved here; add an "authelia/authelia" spec to version-track it.)
THIRD_PARTY_IMAGE_META = {
    "postgres": "18|none",
    "redis": "8|none",
    "rabbitmq": "4|none",
    "qdrant/qdrant": "v1|none",
    "neo4j": "2026|none",
    "ollama/ollama": "0|none",
    "prom/prometheus": "v3|none",
    "grafana/grafana": "13|none",
    "prom/alertmanager": "v0|none",
    "traefik": "v3|none",
    "ghcr.io/wollomatic/socket-proxy": "1|none",
    "influxdb": "3|none",
    "telegraf": "1|none",
    "apicurio/apicurio-registry-sql": "2|none",
    "minio/minio": "RELEASE|none",
    "jaegertracing/all-in-one": "1|none",
    "otel/opentelemetry-collector": "0|none",
    "ghcr.io/open-webui/open-webui": "v0|none",
    "prometheuscommunity/postgres-exporter": "v0|none",
    "oliver006/redis_exporter": "v1|none",
    "kbudde/rabbitmq-exporter": "v1|none",
    "prom/node-exporter": "v1|none",
    "gcr.io/cadvisor/cadvisor": "v0|none",
    "prom/blackbox-exporter": "v0|none",
}

# Health endpoints "port[/path]" (config.sh SERVICE_PORTS). Only services with an
# entry are health-checked. Path defaults to /health when the value is bare port.
# (openwebui/rabbitmq/authelia are Traefik-only (no host port) → intentionally absent.)
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
