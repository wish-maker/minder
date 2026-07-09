# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────

readonly COMPOSE_FILE="${SCRIPT_DIR}/docker/compose/docker-compose.yml"
# Root .env is the SINGLE SOURCE OF TRUTH (one per machine). prepare_env() copies
# it to COMPOSE_ENV_FILE (the path docker compose reads by project-dir default) on
# install/start/restart — see env.sh. ENV_EXAMPLE is the tracked template.
readonly ENV_FILE="${SCRIPT_DIR}/.env"
readonly ENV_EXAMPLE="${SCRIPT_DIR}/.env.example"
readonly COMPOSE_ENV_FILE="${SCRIPT_DIR}/docker/compose/.env"
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
readonly -a CORE_SERVICES=(postgres redis qdrant neo4j rabbitmq )
# ollama is intentionally NOT listed here. It is gated by the compose 'internal-ollama'
# profile (see docker-compose.yml). start_services activates that profile ONLY when
# OLLAMA_BASE_URL is empty (internal mode); naming a profile-disabled service in a
# `compose up` errors ("no such service: ollama: disabled"), so it must not appear.
# - OLLAMA_BASE_URL empty/unset → internal mode: profile active, ollama starts as a
#   dependency of rag-pipeline/openwebui (depends_on … required:false).
# - OLLAMA_BASE_URL set         → external mode: profile inactive, ollama is not part
#   of the project at all → nothing can start it.
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

# Per-image version-resolution METADATA — the knobs compose has no place for.
# The pinned VERSION itself lives ONLY in docker-compose.yml (single source of
# truth); THIRD_PARTY_IMAGE_SPECS is assembled below by pairing each 3rd-party
# compose image with this metadata. This is why a version bump is now a ONE-file
# edit (compose) instead of two — the specs↔compose drift that bit #37 twice is
# structurally impossible now. See #12.
#
#   key   = image ref WITHOUT tag, exactly as written in compose `image:`
#   value = "stable_prefix|constraint"   constraint ∈ {major,minor,patch,none}
declare -A THIRD_PARTY_IMAGE_META=(
    ["postgres"]="18|none"
    ["redis"]="8|none"
    ["rabbitmq"]="4|none"
    ["qdrant/qdrant"]="v1|none"
    ["neo4j"]="2026|none"
    ["ollama/ollama"]="0|none"
    ["prom/prometheus"]="v3|none"
    ["grafana/grafana"]="13|none"
    ["prom/alertmanager"]="v0|none"
    # authelia disabled pending proper configuration (restore when it returns)
    # ["authelia/authelia"]="4|none"
    ["traefik"]="v3|none"
    ["influxdb"]="3|none"
    ["telegraf"]="1|none"
    ["apicurio/apicurio-registry-sql"]="2|none"
    ["minio/minio"]="RELEASE|none"
    ["jaegertracing/all-in-one"]="1|none"
    ["otel/opentelemetry-collector"]="0|none"
    ["ghcr.io/open-webui/open-webui"]="v0|none"
    ["prometheuscommunity/postgres-exporter"]="v0|none"
    ["oliver006/redis_exporter"]="v1|none"
    ["kbudde/rabbitmq-exporter"]="v1|none"
    ["prom/node-exporter"]="v1|none"
    ["gcr.io/cadvisor/cadvisor"]="v0|none"
    ["prom/blackbox-exporter"]="v0|none"
)

# Pull every pinned "image:tag" out of the compose file. Commented lines don't
# match (image: must follow leading whitespace directly), and locally-built
# services (minder/*) are dropped later since they have no metadata entry.
_compose_image_refs() {
    grep -E '^[[:space:]]+image:[[:space:]]+' "$COMPOSE_FILE" \
        | sed -E 's/^[[:space:]]+image:[[:space:]]+//; s/[[:space:]]*(#.*)?$//'
}

# Assemble the version-bearing specs ("image:tag|stable_prefix|constraint" — the
# format the rest of versions.sh consumes) by joining compose images with their
# metadata. Fail-loud on metadata that names an image compose no longer has, so
# an image rename can't silently drop something from update checks.
_derive_third_party_specs() {
    local ref name
    local -A seen=()
    while IFS= read -r ref; do
        [[ -z "$ref" ]] && continue
        name="${ref%:*}"
        if [[ -n "${THIRD_PARTY_IMAGE_META[$name]:-}" ]]; then
            echo "${ref}|${THIRD_PARTY_IMAGE_META[$name]}"
            seen["$name"]=1
        fi
    done < <(_compose_image_refs)

    local key
    for key in "${!THIRD_PARTY_IMAGE_META[@]}"; do
        [[ -z "${seen[$key]:-}" ]] \
            && echo "WARN: THIRD_PARTY_IMAGE_META has '${key}' but no matching image in compose" >&2
    done
    return 0
}

readonly -a THIRD_PARTY_IMAGE_SPECS=($(_derive_third_party_specs))

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

