# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────

readonly COMPOSE_FILE="${SCRIPT_DIR}/docker/compose/docker-compose.yml"
readonly ENV_FILE="${SCRIPT_DIR}/docker/compose/.env"
readonly ENV_EXAMPLE="${SCRIPT_DIR}/docker/compose/.env.example"
readonly LOGS_DIR="${SCRIPT_DIR}/logs"
readonly BACKUP_DIR="${SCRIPT_DIR}/backups"
readonly CACHE_DIR="${SCRIPT_DIR}/.cache"
readonly TAGS_CACHE_DIR="${CACHE_DIR}/tags"
readonly LOG_FILE="${LOGS_DIR}/setup-$(date +%Y%m%d-%H%M%S).log"

# Version resolution cache: image → resolved tag
declare -A RESOLVED_IMAGE_TAGS=()

# Cache configuration
readonly CACHE_TTL_HOURS=24  # Tag cache expires after 24 hours

# ─────────────────────────────────────────────────────────────
# SERVICE DEFINITIONS
# ─────────────────────────────────────────────────────────────

readonly CONTAINER_PREFIX="minder"
readonly NETWORK_NAME="docker_minder-network"
readonly MONITORING_NETWORK_NAME="minder-monitoring"

readonly -a SECURITY_SERVICES=(traefik)
readonly -a CORE_SERVICES=(postgres redis qdrant ollama neo4j rabbitmq )
# Note: ollama uses conditional profiles in docker-compose.yml
# - OLLAMA_BASE_URL empty/unset → local mode, ollama container starts
# - OLLAMA_BASE_URL set → remote mode, ollama container skipped
readonly -a API_SERVICES=(api-gateway plugin-registry marketplace plugin-state-manager rag-pipeline model-management graph-rag)
readonly -a AI_SERVICES=(openwebui tts-stt)
readonly -a MONITORING_SERVICES=(influxdb telegraf prometheus grafana alertmanager jaeger otel-collector)
readonly -a EXPORTER_SERVICES=(postgres-exporter redis-exporter rabbitmq-exporter blackbox-exporter cadvisor node-exporter)

# Port map  service-name → port/path  (used by health checks)
declare -A SERVICE_PORTS=(
    [api-gateway]="8000/health"
    [plugin-registry]="8001/health"
    [marketplace]="8002/health"
    [plugin-state-manager]="8003/health"
    [rag-pipeline]="8004/health"
    [model-management]="8005/health"
    [tts-stt]="8006/health"
    [graph-rag]="8008/health"
    # OpenWebUI port not exposed (Traefik only), skipping direct health check
    [prometheus]="9090/-/healthy"
    [grafana]="3000/api/health"
    [influxdb]="8086"
    [traefik]="8081/dashboard/"
    # RabbitMQ management UI port not exposed (Traefik only), skipping direct health check
    # authelia disabled pending proper configuration
    # [authelia]="9091/api/health"
    [minio]="9000/minio/health/live"
    [jaeger]="16686"
    [otel-collector]="18888/metrics"
)

# ─────────────────────────────────────────────────────────────
# IMAGE REGISTRY DEFINITIONS
#
# Format:  "<image_ref>|<stable_tag>|<version_constraint>"
#
# Fields:
#   image_ref          — registry/repo:pinned-tag  (fallback if latest fails)
#   stable_tag         — the "safe" semver prefix to query for  e.g. "16" means
#                        accept 16.x.x but NOT 17.x.x  (major-version pinning)
#   version_constraint — "major" | "minor" | "patch" | "none"
#                        controls how aggressively we update:
#                          major → only accept same major
#                          minor → only accept same major.minor
#                          patch → only accept same major.minor.patch (= never update)
#                          none  → accept any newer version
#
# The resolver first contacts the appropriate registry API, finds the newest
# tag matching the constraint, then attempts to pull it.  If the pull fails
# (bad manifest, network error, incompatible image) it logs a warning and
# falls back to the exact pinned tag automatically.
# ─────────────────────────────────────────────────────────────

readonly -a THIRD_PARTY_IMAGE_SPECS=(
    # image_ref                                              | stable_tag | constraint
    "postgres:18.4-trixie|18|none"
    "redis:8.8.0-alpine|8|none"
    "rabbitmq:4.3.2-management|4|none"
    "qdrant/qdrant:v1.18.2|v1|none"
    "neo4j:2026.05.0-community|2026|none"
    "ollama/ollama:0.30.10|0|none"
    "prom/prometheus:v3.12.0|v3|none"
    "grafana/grafana:13.1|13|none"
    "prom/alertmanager:v0.33.0|v0|none"
    # authelia disabled pending proper configuration
    # "authelia/authelia:4.38.7|4|none"
    "traefik:v3.7.5|v3|none"
    "influxdb:3.10.0-core|3|none"
    "telegraf:1.39.0|1|none"
    "apicurio/apicurio-registry-sql:2.6.13.Final|2|none"
    "minio/minio:RELEASE.2025-09-07T16-13-09Z|RELEASE|none"
    "jaegertracing/all-in-one:latest|1|none"
    "otel/opentelemetry-collector:0.155.0|0|none"
    "ghcr.io/open-webui/open-webui:latest|main|none"
    "prometheuscommunity/postgres-exporter:v0.19.1|v0|none"
    "oliver006/redis_exporter:v1.86.0|v1|none"
    "kbudde/rabbitmq-exporter:v1.0.0-RC9|v1|none"
    "prom/node-exporter:v1.11.1|v1|none"
    "gcr.io/cadvisor/cadvisor:v0.51.0|v0|none"
    "prom/blackbox-exporter:v0.28.0|v0|none"
)

# Build a plain array of pinned image refs (for backward compat / fallback)
readonly -a THIRD_PARTY_IMAGES=($(
    for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do
        echo "${spec%%|*}"
    done
))

# Timeouts (seconds)
readonly TIMEOUT_DB=60
readonly TIMEOUT_SERVICES=90
readonly TIMEOUT_MONITORING=120
readonly TIMEOUT_AI=120
readonly TIMEOUT_OLLAMA=90
readonly TIMEOUT_PORT=30
readonly TIMEOUT_REGISTRY=8      # per registry HTTP call

# ─────────────────────────────────────────────────────────────
# RUNTIME FLAGS
# ─────────────────────────────────────────────────────────────

DRY_RUN="${DRY_RUN:-false}"
CLEAN_DANGLING="${CLEAN_DANGLING:-false}"
JSON_OUTPUT=false
VERBOSE=false
SKIP_VERSION_CHECK="${SKIP_VERSION_CHECK:-false}"   # bypass registry queries

# Detect non-interactive / CI mode
if [[ ! -t 0 ]] || [[ "${CI:-false}" == "true" ]] || [[ "${NONINTERACTIVE:-false}" == "true" ]]; then
    INTERACTIVE=false
else
    INTERACTIVE=true
fi

# ─────────────────────────────────────────────────────────────
# COLORS  (disabled when not a real terminal)
# ─────────────────────────────────────────────────────────────

if [[ -t 1 ]] && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
    RED='\033[0;31m';    GREEN='\033[0;32m';   YELLOW='\033[1;33m'
    BLUE='\033[0;34m';   MAGENTA='\033[0;35m'; CYAN='\033[0;36m'
    BOLD='\033[1m';      DIM='\033[2m';         NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; BLUE=''; MAGENTA=''; CYAN=''; BOLD=''; DIM=''; NC=''
fi

readonly SPINNER_FRAMES=("⠋" "⠙" "⠹" "⠸" "⠼" "⠴" "⠦" "⠧" "⠇" "⠏")
SPINNER_PID=""

