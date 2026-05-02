#!/usr/bin/env bash
###############################################################################
# Minder Platform — Setup & Lifecycle Management Script
# Version: 1.0.0
#
# FEATURES:
#   • Full install / start / stop / restart / status / logs
#   • Comprehensive backup  (Postgres, Neo4j, InfluxDB, Qdrant, .env)
#   • restore  — restore from a backup directory
#   • migrate  — run Alembic DB migrations inside running containers
#   • doctor   — deep diagnostic: disk, ports, secrets, images, version drift
#   • update   — pull latest images, rebuild customs, rolling restart
#   • update --check  — report available updates without applying
#   • shell    — drop into a container shell
#   • Smart version resolution: try latest → fall back to pinned on failure
#   • Structured JSON health report  (--json flag on status)
#   • Dry-run mode  (DRY_RUN=1 ./setup.sh start)
#   • CI/non-interactive mode detection
#   • Trap-based cleanup on unexpected exit
#   • Full audit log in logs/setup-<timestamp>.log
###############################################################################

set -euo pipefail
IFS=$'\n\t'

# ─────────────────────────────────────────────────────────────
# SCRIPT METADATA
# ─────────────────────────────────────────────────────────────

readonly SCRIPT_VERSION="1.0.0"
readonly SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─────────────────────────────────────────────────────────────
# PATHS
# ─────────────────────────────────────────────────────────────

readonly COMPOSE_FILE="${SCRIPT_DIR}/infrastructure/docker/docker-compose.yml"
readonly ENV_FILE="${SCRIPT_DIR}/infrastructure/docker/.env"
readonly ENV_EXAMPLE="${SCRIPT_DIR}/infrastructure/docker/.env.example"
readonly LOGS_DIR="${SCRIPT_DIR}/logs"
readonly BACKUP_DIR="${SCRIPT_DIR}/backups"
readonly LOG_FILE="${LOGS_DIR}/setup-$(date +%Y%m%d-%H%M%S).log"

# Version resolution cache: image → resolved tag
declare -A RESOLVED_IMAGE_TAGS=()

# ─────────────────────────────────────────────────────────────
# SERVICE DEFINITIONS
# ─────────────────────────────────────────────────────────────

readonly CONTAINER_PREFIX="minder"
readonly NETWORK_NAME="docker_minder-network"

readonly -a SECURITY_SERVICES=(traefik authelia)
readonly -a CORE_SERVICES=(postgres redis qdrant ollama neo4j)
readonly -a API_SERVICES=(api-gateway plugin-registry marketplace plugin-state-manager rag-pipeline model-management)
readonly -a AI_SERVICES=(openwebui tts-stt-service model-fine-tuning)
readonly -a MONITORING_SERVICES=(influxdb telegraf prometheus grafana alertmanager)
readonly -a EXPORTER_SERVICES=(postgres-exporter redis-exporter)

# Port map  service-name → port/path  (used by health checks)
declare -A SERVICE_PORTS=(
    [api-gateway]="8000/health"
    [plugin-registry]="8001/health"
    [marketplace]="8002/health"
    [plugin-state-manager]="8003/health"
    [rag-pipeline]="8004/health"
    [model-management]="8005/health"
    [tts-stt-service]="8006/health"
    [model-fine-tuning]="8007/health"
    [openwebui]="8080"
    [prometheus]="9090/-/healthy"
    [grafana]="3000/api/health"
    [influxdb]="8086/ping"
    [traefik]="8081/ping"
    [authelia]="9091/api/health"
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
    "postgres:16|16|major"
    "redis:7.2-alpine|7|major"
    "qdrant/qdrant:v1.17.1|v1|major"
    "neo4j:5.24-community|5|major"
    "ollama/ollama:0.5.7|0|minor"
    "prom/prometheus:v2.55.1|v2|major"
    "grafana/grafana:11.4.0|11|major"
    "prom/alertmanager:v0.28.1|v0|major"
    "authelia/authelia:4.38.7|4|major"
    "traefik:v3.1.6|v3|major"
    "influxdb:2.7.12|2|major"
    "telegraf:1.33.1|1|major"
    "prometheuscommunity/postgres-exporter:v0.15.0|v0|minor"
    "oliver006/redis_exporter:v1.62.0|v1|major"
    "ghcr.io/open-webui/open-webui:git-69d0a16|main|none"
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

# ─────────────────────────────────────────────────────────────
# TRAP — cleanup on unexpected exit
# ─────────────────────────────────────────────────────────────

_cleanup() {
    local exit_code=$?
    spinner_stop
    if (( exit_code != 0 )); then
        echo -e "\n${RED}✗ Script exited unexpectedly (code ${exit_code})${NC}"
        echo -e "${DIM}Full log: ${LOG_FILE}${NC}"
    fi
}
trap _cleanup EXIT

# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────

mkdir -p "$LOGS_DIR"

_log() {
    local level="$1" icon="$2" color="$3"
    shift 3
    local msg="$*"
    local ts; ts="$(date '+%H:%M:%S')"
    echo -e "${color}${icon}${NC} ${DIM}${ts}${NC}  ${msg}"
    local plain; plain="$(echo -e "$msg" | sed 's/\x1b\[[0-9;]*m//g')"
    echo "[${ts}] [${level}] ${plain}" >> "$LOG_FILE" 2>/dev/null || true
}

log_info()    { _log "INFO"  "ℹ"  "${BLUE}"    "$@"; }
log_success() { _log "OK"    "✓"  "${GREEN}"   "${GREEN}$*${NC}"; }
log_warn()    { _log "WARN"  "⚠"  "${YELLOW}"  "${YELLOW}$*${NC}"; }
log_error()   { _log "ERROR" "✗"  "${RED}"     "${RED}$*${NC}"; }
log_debug()   { [[ "$VERBOSE" == "true" ]] && _log "DEBUG" "·" "${DIM}" "$@" || true; }
log_step()    { echo -e "\n${BOLD}${CYAN}▸ $*${NC}"; echo "[STEP] $*" >> "$LOG_FILE" 2>/dev/null || true; }
log_detail()  { echo -e "  ${DIM}$*${NC}"; }

section() {
    local title="$1"
    echo ""
    echo -e "${BOLD}${MAGENTA}┌──────────────────────────────────────────────────┐${NC}"
    printf  "${BOLD}${MAGENTA}│${NC}  %-48s${BOLD}${MAGENTA}│${NC}\n" "$title"
    echo -e "${BOLD}${MAGENTA}└──────────────────────────────────────────────────┘${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────
# SPINNER
# ─────────────────────────────────────────────────────────────

spinner_start() {
    spinner_stop
    local msg="$1"
    (
        local i=0
        while true; do
            printf "\r${CYAN}${SPINNER_FRAMES[$((i % 10))]}${NC}  %-60s" "$msg"
            sleep 0.1
            i=$(( i + 1 ))
        done
    ) &
    SPINNER_PID=$!
    disown "$SPINNER_PID" 2>/dev/null || true
}

spinner_stop() {
    if [[ -n "${SPINNER_PID:-}" ]]; then
        kill "$SPINNER_PID" 2>/dev/null || true
        wait "$SPINNER_PID" 2>/dev/null || true
        SPINNER_PID=""
    fi
    printf "\r\033[K"
}

# ─────────────────────────────────────────────────────────────
# PROGRESS BAR
# ─────────────────────────────────────────────────────────────

PROGRESS_STEP=0
PROGRESS_TOTAL=9

progress_init() { PROGRESS_TOTAL="$1"; PROGRESS_STEP=0; }

progress_next() {
    local label="$1"
    PROGRESS_STEP=$(( PROGRESS_STEP + 1 ))
    local pct=$(( PROGRESS_STEP * 100 / PROGRESS_TOTAL ))
    local filled=$(( pct / 5 ))
    local empty=$(( 20 - filled ))
    local bar=""
    for (( i=0; i<filled; i++ )); do bar+="█"; done
    for (( i=0; i<empty;  i++ )); do bar+="░"; done
    echo ""
    echo -e "${BOLD}[${PROGRESS_STEP}/${PROGRESS_TOTAL}]${NC} ${label}"
    echo -e "${CYAN}${bar}${NC} ${DIM}${pct}%${NC}"
}

# ─────────────────────────────────────────────────────────────
# DRY RUN WRAPPER
# ─────────────────────────────────────────────────────────────

run() {
    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${DIM}[dry-run] $*${NC}"
        return 0
    fi
    "$@"
}

# ─────────────────────────────────────────────────────────────
# DOCKER HELPERS
# ─────────────────────────────────────────────────────────────

compose() {
    run docker compose -f "$COMPOSE_FILE" "$@"
}

compose_monitoring() {
    run docker compose -f "$COMPOSE_FILE" --profile monitoring "$@"
}

container_name() { echo "${CONTAINER_PREFIX}-${1}"; }

container_running() {
    docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^$(container_name "$1")$"
}

container_health() {
    docker inspect --format='{{.State.Health.Status}}' "$(container_name "$1")" 2>/dev/null || echo "n/a"
}

container_exists() {
    docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q "^$(container_name "$1")$"
}

# ─────────────────────────────────────────────────────────────
# WAIT / POLL HELPERS
# ─────────────────────────────────────────────────────────────

wait_healthy() {
    local svc="$1" timeout="${2:-$TIMEOUT_SERVICES}"
    local elapsed=0

    spinner_start "Waiting for ${svc}…"
    while (( elapsed < timeout )); do
        local s; s="$(container_health "$svc")"
        if [[ "$s" == "healthy" ]]; then
            spinner_stop
            log_success "${svc} is healthy"
            return 0
        fi
        sleep 3; elapsed=$(( elapsed + 3 ))
    done
    spinner_stop
    log_warn "${svc} not healthy after ${timeout}s  (status: $(container_health "$svc"))"
    return 1
}

wait_port() {
    local host="$1" port="$2" timeout="${3:-$TIMEOUT_PORT}"
    local elapsed=0
    while (( elapsed < timeout )); do
        if 2>/dev/null >/dev/tcp/"$host"/"$port"; then return 0; fi
        sleep 2; elapsed=$(( elapsed + 2 ))
    done
    return 1
}

wait_postgres_ready() {
    local timeout="${1:-$TIMEOUT_DB}"
    local elapsed=0
    spinner_start "Waiting for PostgreSQL…"
    while (( elapsed < timeout )); do
        if docker exec "$(container_name postgres)" pg_isready -U minder &>/dev/null 2>&1; then
            spinner_stop
            log_success "PostgreSQL is ready"
            return 0
        fi
        sleep 2; elapsed=$(( elapsed + 2 ))
    done
    spinner_stop
    log_error "PostgreSQL did not become ready within ${timeout}s"
    return 1
}

# ─────────────────────────────────────────────────────────────
# SECRET GENERATION
# ─────────────────────────────────────────────────────────────

gen_secret() {
    local bytes="${1:-32}"
    if command -v openssl &>/dev/null; then
        openssl rand -hex "$bytes"
    else
        LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom | head -c $(( bytes * 2 ))
    fi
}

# ─────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════
#  SMART VERSION RESOLUTION ENGINE
# ════════════════════════════════════════════════════════════
#
#  Strategy:
#    1. Parse the spec  (image:pinned_tag | stable_prefix | constraint)
#    2. Query the appropriate registry API for available tags
#    3. Filter tags that satisfy the version constraint
#    4. Select the highest satisfying version
#    5. Attempt docker pull of that version
#    6. On any failure → fall back to the exact pinned tag silently
#
#  Registry drivers:
#    • dockerhub_latest_tag()  — Docker Hub  (hub.docker.com)
#    • ghcr_latest_tag()       — GitHub Container Registry  (ghcr.io)
#    • quay_latest_tag()       — Quay.io  (quay.io)
# ─────────────────────────────────────────────────────────────

# Detect which registry an image ref belongs to
_registry_type() {
    local image_ref="$1"
    case "$image_ref" in
        ghcr.io/*)  echo "ghcr" ;;
        quay.io/*)  echo "quay" ;;
        *)          echo "dockerhub" ;;
    esac
}

# Strip registry prefix to get repo path  (e.g. ghcr.io/foo/bar → foo/bar)
_image_repo() {
    local image_ref="$1"
    local no_tag="${image_ref%%:*}"
    case "$no_tag" in
        ghcr.io/*)  echo "${no_tag#ghcr.io/}" ;;
        quay.io/*)  echo "${no_tag#quay.io/}" ;;
        */*)        echo "$no_tag" ;;          # already  org/repo
        *)          echo "library/${no_tag}" ;;# official image  e.g. postgres → library/postgres
    esac
}

# ── Docker Hub tag query ──────────────────────────────────────
# Returns a newline-separated list of tags for a Docker Hub repo.
# Docker Hub returns max 100 tags per page; we only fetch page 1
# (newest tags appear first when ordered by last_updated desc).
dockerhub_list_tags() {
    local repo="$1"   # e.g. library/postgres  or  grafana/grafana
    local url="https://hub.docker.com/v2/repositories/${repo}/tags?page_size=100&ordering=last_updated"
    local response
    if ! response="$(curl -sf --max-time "${TIMEOUT_REGISTRY}" "$url" 2>/dev/null)"; then
        log_debug "dockerhub_list_tags: HTTP request failed for ${repo}"
        echo ""
        return 1
    fi
    # Extract "name" fields from the JSON array using pure bash + grep/sed
    # (avoids jq dependency)
    echo "$response" \
        | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
        | sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//'
}

# ── GHCR tag query ────────────────────────────────────────────
# GHCR exposes the OCI Distribution Spec tag listing endpoint.
# No auth needed for public packages.
ghcr_list_tags() {
    local repo="$1"   # e.g. open-webui/open-webui
    local url="https://ghcr.io/v2/${repo}/tags/list"
    local response
    if ! response="$(curl -sf --max-time "${TIMEOUT_REGISTRY}" \
            -H "Accept: application/json" "$url" 2>/dev/null)"; then
        log_debug "ghcr_list_tags: HTTP request failed for ${repo}"
        echo ""
        return 1
    fi
    echo "$response" \
        | grep -oE '"[^"]+"' \
        | sed 's/"//g' \
        | grep -v '^tags$\|^name$\|^\{$\|^\}$'
}

# ── Quay.io tag query ─────────────────────────────────────────
quay_list_tags() {
    local repo="$1"   # e.g. prometheus/prometheus
    local url="https://quay.io/api/v1/repository/${repo}/tag/?limit=100&onlyActiveTags=true"
    local response
    if ! response="$(curl -sf --max-time "${TIMEOUT_REGISTRY}" "$url" 2>/dev/null)"; then
        log_debug "quay_list_tags: HTTP request failed for ${repo}"
        echo ""
        return 1
    fi
    echo "$response" \
        | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
        | sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//'
}

# ── Version comparison helpers ────────────────────────────────

# Strips leading 'v' so v1.2.3 and 1.2.3 compare equal
_strip_v() { echo "${1#v}"; }

# Returns 0 if $1 >= $2  (semver-ish, dot-separated numeric)
_ver_ge() {
    local a="$(_strip_v "$1")" b="$(_strip_v "$2")"
    # Use sort -V if available, otherwise fall back to string compare
    if printf '%s\n%s\n' "$b" "$a" | sort -V --check=quiet 2>/dev/null; then
        return 0
    elif [[ "$(printf '%s\n%s\n' "$b" "$a" | sort -V 2>/dev/null | head -1)" == "$b" ]]; then
        return 0
    else
        return 1
    fi
}

# Checks if tag satisfies the constraint relative to the stable_prefix.
# constraint = major  → tag must share same major version number
# constraint = minor  → tag must share same major.minor
# constraint = none   → any version accepted
# constraint = patch  → tag must exactly equal pinned (handled upstream)
_tag_satisfies_constraint() {
    local tag="$1" stable_prefix="$2" constraint="$3"
    local t; t="$(_strip_v "$tag")"
    local p; p="$(_strip_v "$stable_prefix")"

    # Reject non-numeric tags (latest, main, edge, nightly, rc*, beta*, alpha*, git-*)
    if [[ ! "$t" =~ ^[0-9]+(\.[0-9]+)*(-[a-zA-Z0-9]+)?$ ]] || \
       [[ "$t" =~ (rc|alpha|beta|dev|nightly|edge|test) ]]; then
        return 1
    fi

    local t_major; t_major="$(echo "$t" | cut -d. -f1)"
    local p_major; p_major="$(echo "$p" | cut -d. -f1)"

    case "$constraint" in
        major)
            [[ "$t_major" == "$p_major" ]]
            ;;
        minor)
            local t_minor; t_minor="$(echo "$t" | cut -d. -f1-2)"
            local p_minor; p_minor="$(echo "$p" | cut -d. -f1-2)"
            [[ "$t_minor" == "$p_minor" ]]
            ;;
        none)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}

# Select the highest version from a tag list satisfying the constraint
_best_tag() {
    local tags="$1" stable_prefix="$2" constraint="$3"
    local best=""
    while IFS= read -r tag; do
        [[ -z "$tag" ]] && continue
        if _tag_satisfies_constraint "$tag" "$stable_prefix" "$constraint"; then
            if [[ -z "$best" ]] || _ver_ge "$tag" "$best"; then
                best="$tag"
            fi
        fi
    done <<< "$tags"
    echo "$best"
}

# ── Main resolver ─────────────────────────────────────────────
#
# resolve_image_tag <spec_string>
#
# Writes the resolved full image ref to RESOLVED_IMAGE_TAGS[<pinned_ref>]
# and echoes the resolved ref.
# Falls back to the pinned ref if resolution or pull fails.
#
resolve_image_tag() {
    local spec="$1"
    local pinned_ref stable_prefix constraint
    IFS='|' read -r pinned_ref stable_prefix constraint <<< "$spec"

    # Cache hit
    if [[ -v "RESOLVED_IMAGE_TAGS[$pinned_ref]" ]]; then
        echo "${RESOLVED_IMAGE_TAGS[$pinned_ref]}"
        return 0
    fi

    # Short-circuit: patch constraint or check disabled → always use pin
    if [[ "$constraint" == "patch" ]] || [[ "$SKIP_VERSION_CHECK" == "true" ]]; then
        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$pinned_ref"
        echo "$pinned_ref"
        return 0
    fi

    local image_base="${pinned_ref%%:*}"
    local pinned_tag="${pinned_ref##*:}"
    local registry; registry="$(_registry_type "$pinned_ref")"
    local repo; repo="$(_image_repo "$pinned_ref")"

    log_debug "Querying ${registry} for ${repo} (prefix=${stable_prefix}, constraint=${constraint})"

    # Fetch tag list from the appropriate registry
    local all_tags=""
    case "$registry" in
        ghcr)       all_tags="$(ghcr_list_tags "$repo" 2>/dev/null || true)" ;;
        quay)       all_tags="$(quay_list_tags "$repo" 2>/dev/null || true)" ;;
        dockerhub)  all_tags="$(dockerhub_list_tags "$repo" 2>/dev/null || true)" ;;
    esac

    if [[ -z "$all_tags" ]]; then
        log_debug "No tags retrieved for ${repo} — using pinned ${pinned_ref}"
        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$pinned_ref"
        echo "$pinned_ref"
        return 0
    fi

    # Find the best matching tag
    local best_tag; best_tag="$(_best_tag "$all_tags" "$stable_prefix" "$constraint")"

    if [[ -z "$best_tag" ]]; then
        log_debug "No satisfying tag found for ${repo} — using pinned ${pinned_ref}"
        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$pinned_ref"
        echo "$pinned_ref"
        return 0
    fi

    # Reconstruct full image ref (preserve registry prefix)
    local candidate_ref
    case "$registry" in
        ghcr) candidate_ref="ghcr.io/${repo}:${best_tag}" ;;
        quay) candidate_ref="quay.io/${repo}:${best_tag}" ;;
        *)    candidate_ref="${image_base}:${best_tag}" ;;
    esac

    # If candidate == pinned, nothing to try
    if [[ "$candidate_ref" == "$pinned_ref" ]]; then
        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$pinned_ref"
        echo "$pinned_ref"
        return 0
    fi

    log_debug "Candidate: ${candidate_ref}  (pinned: ${pinned_ref})"

    # ── Try pulling the candidate ──────────────────────────────
    # We do a manifest inspect first (cheap, no layer download) to validate
    # the image exists and is compatible before committing to a full pull.
    spinner_start "Resolving ${image_base}: ${pinned_tag} → ${best_tag}?"

    local manifest_ok=false
    if docker manifest inspect "${candidate_ref}" &>/dev/null 2>&1; then
        manifest_ok=true
    fi

    if [[ "$manifest_ok" == "true" ]]; then
        spinner_stop
        log_success "${image_base}: ${pinned_tag} → ${CYAN}${best_tag}${NC}  (latest compatible)"
        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$candidate_ref"
        echo "$candidate_ref"
    else
        spinner_stop
        log_warn "${image_base}: ${best_tag} manifest check failed — falling back to pinned ${pinned_tag}"
        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$pinned_ref"
        echo "$pinned_ref"
    fi
}

# ── Pull a single image with automatic fallback ───────────────
#
# pull_image_with_fallback <spec_string>
#
# 1. Resolves best tag via resolve_image_tag
# 2. Attempts docker pull of the resolved ref
# 3. On pull failure → pulls the exact pinned ref instead
# Returns 0 always (non-fatal; individual image failures are logged)
#
pull_image_with_fallback() {
    local spec="$1"
    local pinned_ref; pinned_ref="${spec%%|*}"
    local pinned_tag="${pinned_ref##*:}"
    local image_base="${pinned_ref%%:*}"

    # Resolve (may return candidate or pinned)
    local target_ref; target_ref="$(resolve_image_tag "$spec")"

    spinner_start "Pulling ${target_ref}…"
    if run docker pull "$target_ref" &>/dev/null 2>&1; then
        spinner_stop
        log_success "${target_ref}"
        return 0
    fi
    spinner_stop

    # Pull of resolved ref failed
    if [[ "$target_ref" != "$pinned_ref" ]]; then
        log_warn "${target_ref} pull failed — falling back to pinned ${pinned_ref}"
        spinner_start "Pulling ${pinned_ref} (fallback)…"
        if run docker pull "$pinned_ref" &>/dev/null 2>&1; then
            spinner_stop
            log_success "${pinned_ref}  ${DIM}(pinned fallback)${NC}"
            # Update cache to reflect we're on the pin
            RESOLVED_IMAGE_TAGS["$pinned_ref"]="$pinned_ref"
            return 0
        fi
        spinner_stop
        log_warn "${pinned_ref} also failed — image may already be cached locally"
    else
        log_warn "${pinned_ref} pull failed — image may already be cached locally"
    fi

    return 0   # non-fatal
}

# Pull all third-party images with version resolution
pull_all_images() {
    section "📦  Pulling Images  (smart version resolution)"
    log_info "Constraint legend: major=same major OK · minor=same major.minor OK · none=any"
    echo ""

    for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do
        pull_image_with_fallback "$spec"
    done

    log_success "Image pull phase complete"
}

# ─────────────────────────────────────────────────────────────
# VERSION DRIFT REPORT  (used by doctor and update --check)
# ─────────────────────────────────────────────────────────────

version_drift_report() {
    local json_mode="${1:-false}"
    local -a drift_items=()
    local -a ok_items=()

    for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do
        local pinned_ref stable_prefix constraint
        IFS='|' read -r pinned_ref stable_prefix constraint <<< "$spec"
        local pinned_tag="${pinned_ref##*:}"
        local image_base="${pinned_ref%%:*}"

        # Resolve without pulling (manifest inspect only)
        local resolved; resolved="$(resolve_image_tag "$spec")"
        local resolved_tag="${resolved##*:}"

        if [[ "$resolved_tag" != "$pinned_tag" ]] && [[ "$resolved_tag" != "" ]]; then
            drift_items+=("${image_base}|${pinned_tag}|${resolved_tag}|${constraint}")
        else
            ok_items+=("${image_base}|${pinned_tag}|${constraint}")
        fi
    done

    if [[ "$json_mode" == "true" ]]; then
        echo "{"
        echo "  \"timestamp\": \"$(date -u +%FT%TZ)\","
        echo "  \"updates_available\": ${#drift_items[@]},"
        echo "  \"drift\": ["
        local first=true
        for item in "${drift_items[@]}"; do
            local img cur avail con
            IFS='|' read -r img cur avail con <<< "$item"
            [[ "$first" == false ]] && echo ","
            printf '    {"image":"%s","current":"%s","available":"%s","constraint":"%s"}' \
                "$img" "$cur" "$avail" "$con"
            first=false
        done
        echo ""
        echo "  ]"
        echo "}"
        return
    fi

    echo -e "\n${BOLD}Version Drift Report${NC}"
    if (( ${#drift_items[@]} == 0 )); then
        log_success "All images are up to date ✓"
    else
        echo -e "  ${YELLOW}${#drift_items[@]} update(s) available:${NC}\n"
        printf "  %-45s  %-20s  %-20s  %s\n" "IMAGE" "CURRENT" "AVAILABLE" "CONSTRAINT"
        printf "  %-45s  %-20s  %-20s  %s\n" "─────" "───────" "─────────" "──────────"
        for item in "${drift_items[@]}"; do
            local img cur avail con
            IFS='|' read -r img cur avail con <<< "$item"
            printf "  ${CYAN}%-45s${NC}  ${DIM}%-20s${NC}  ${GREEN}%-20s${NC}  %s\n" \
                "$img" "$cur" "$avail" "$con"
        done
        echo ""
        log_detail "Apply updates:   ./${SCRIPT_NAME} update"
        log_detail "Skip and use pins: SKIP_VERSION_CHECK=1 ./${SCRIPT_NAME} update"
    fi

    if (( ${#ok_items[@]} > 0 )) && [[ "$VERBOSE" == "true" ]]; then
        echo -e "\n  ${DIM}Up to date:${NC}"
        for item in "${ok_items[@]}"; do
            local img cur con; IFS='|' read -r img cur con <<< "$item"
            log_detail "  ✓  ${img}:${cur}  (${con})"
        done
    fi
}

# ─────────────────────────────────────────────────────────────
# PREREQUISITE CHECK
# ─────────────────────────────────────────────────────────────

check_prerequisites() {
    log_step "Checking prerequisites"
    local failed=0

    if ! command -v docker &>/dev/null; then
        log_error "Docker not installed → https://docs.docker.com/get-docker/"
        failed=1
    else
        log_detail "Docker $(docker --version | awk '{print $3}' | tr -d ',')"
    fi

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose v2 not available → https://docs.docker.com/compose/install/"
        failed=1
    else
        log_detail "Compose $(docker compose version --short 2>/dev/null || echo 'v2')"
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker daemon is not running — start Docker Desktop or dockerd"
        failed=1
    fi

    if ! command -v openssl &>/dev/null; then
        log_warn "openssl not found — falling back to /dev/urandom for secret generation"
    fi

    if ! command -v curl &>/dev/null; then
        log_warn "curl not found — smart version resolution will be skipped"
        SKIP_VERSION_CHECK=true
    fi

    if [[ ! -f "$COMPOSE_FILE" ]]; then
        log_error "Compose file not found: ${COMPOSE_FILE}"
        failed=1
    else
        log_detail "Compose file: ${COMPOSE_FILE}"
    fi

    local free_gb
    free_gb="$(df -BG "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2{gsub("G",""); print $4}' || echo 999)"
    if (( free_gb < 10 )); then
        log_warn "Low disk space: ${free_gb}GB free (recommend ≥10GB)"
    else
        log_detail "Disk space: ${free_gb}GB free"
    fi

    local busy_ports=()
    for port in 5432 6379 8000 8001 8002 8003 8004 8005 8006 8007 8080 8081 8086 9090 9091 3000; do
        if 2>/dev/null >/dev/tcp/127.0.0.1/"$port"; then
            if ! docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                busy_ports+=("$port")
            fi
        fi
    done
    if (( ${#busy_ports[@]} > 0 )); then
        log_warn "Ports already in use (may conflict): ${busy_ports[*]}"
    fi

    if (( failed )); then
        log_error "Prerequisites failed — cannot continue"
        exit 1
    fi

    log_success "All prerequisites satisfied"
}

# ─────────────────────────────────────────────────────────────
# ENVIRONMENT SETUP
# ─────────────────────────────────────────────────────────────

setup_environment() {
    log_step "Setting up environment"

    if [[ -f "$ENV_FILE" ]]; then
        log_info ".env already exists — skipping generation"
        log_detail "Remove ${ENV_FILE} and re-run to regenerate secrets"
        _validate_env
        return 0
    fi

    mkdir -p "$(dirname "$ENV_FILE")"

    if [[ -f "$ENV_EXAMPLE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        log_success "Copied .env from .env.example"
        _fill_env_secrets
    else
        log_info "No .env.example found — generating configuration"
        _write_default_env
    fi

    chmod 600 "$ENV_FILE"
    log_detail "Permissions set to 600 on .env"
    log_success "Environment ready"
}

_write_default_env() {
    cat > "$ENV_FILE" << EOF
# Minder Platform — Environment Configuration
# Generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')
# ⚠  Keep this file secret. Never commit to version control.

# ── PostgreSQL ───────────────────────────────────────────────
POSTGRES_USER=minder
POSTGRES_PASSWORD=$(gen_secret 32)
POSTGRES_DB=minder

# ── Redis ────────────────────────────────────────────────────
REDIS_PASSWORD=$(gen_secret 32)

# ── Auth & Security ──────────────────────────────────────────
JWT_SECRET=$(gen_secret 64)
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# ── Neo4j ────────────────────────────────────────────────────
NEO4J_AUTH=neo4j/$(gen_secret 16)

# ── InfluxDB ─────────────────────────────────────────────────
INFLUXDB_ADMIN_TOKEN=$(gen_secret 40)
INFLUXDB_ORG=minder
INFLUXDB_BUCKET=metrics

# ── Ollama ───────────────────────────────────────────────────
OLLAMA_AUTOMATIC_PULL=true
OLLAMA_MODELS=llama3.2,nomic-embed-text

# ── Application ──────────────────────────────────────────────
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF
    log_success "Generated .env with secure random secrets"
}

_fill_env_secrets() {
    local changed=0
    while IFS= read -r line; do
        if [[ "$line" =~ ^([A-Z_]+)=(CHANGEME|REPLACE_ME|)$ ]]; then
            local key="${BASH_REMATCH[1]}"
            local secret; secret="$(gen_secret 32)"
            sed -i "s|^${key}=.*|${key}=${secret}|" "$ENV_FILE"
            log_detail "Generated secret for ${key}"
            changed=$(( changed + 1 ))
        fi
    done < "$ENV_FILE"
    (( changed > 0 )) && log_success "${changed} placeholder secret(s) replaced"
}

_validate_env() {
    local required_keys=(POSTGRES_USER POSTGRES_PASSWORD REDIS_PASSWORD JWT_SECRET NEO4J_AUTH)
    local missing=()
    for key in "${required_keys[@]}"; do
        if ! grep -qE "^${key}=.+" "$ENV_FILE"; then
            missing+=("$key")
        fi
    done
    if (( ${#missing[@]} > 0 )); then
        log_warn "Missing or empty keys in .env: ${missing[*]}"
        log_detail "Run './setup.sh doctor' for full diagnostics"
    fi
}

_env_get() {
    grep -E "^${1}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo ""
}

# ─────────────────────────────────────────────────────────────
# NETWORK
# ─────────────────────────────────────────────────────────────

create_networks() {
    log_step "Setting up Docker network"
    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        log_info "Network '${NETWORK_NAME}' already exists"
    else
        run docker network create "$NETWORK_NAME"
        log_success "Network '${NETWORK_NAME}' created"
    fi
}

# ─────────────────────────────────────────────────────────────
# DATABASE INITIALISATION
# ─────────────────────────────────────────────────────────────

readonly -a EXTRA_DATABASES=(minder_marketplace tefas_db weather_db news_db crypto_db minder_authelia)

initialize_database() {
    log_step "Initialising databases"

    compose up -d postgres
    wait_postgres_ready || exit 1

    log_info "Creating auxiliary databases…"
    for db in "${EXTRA_DATABASES[@]}"; do
        if docker exec "$(container_name postgres)" psql -U minder \
               -c "CREATE DATABASE ${db};" &>/dev/null 2>&1; then
            log_detail "Created: ${db}"
        else
            log_detail "Already exists: ${db}"
        fi
    done

    log_success "Database initialisation complete"
}

# ─────────────────────────────────────────────────────────────
# SERVICE STARTUP
# ─────────────────────────────────────────────────────────────

start_services() {
    log_step "Starting all services"

    log_info "① Security layer…"
    compose up -d "${SECURITY_SERVICES[@]}"
    sleep 5

    log_info "② Infrastructure (DB, cache, vector store, AI runtime)…"
    compose up -d "${CORE_SERVICES[@]}"
    sleep 8

    log_info "③ Core microservices…"
    compose up -d "${API_SERVICES[@]}"
    sleep 5

    log_info "④ Monitoring stack…"
    compose up -d influxdb telegraf
    compose_monitoring up -d prometheus grafana alertmanager
    sleep 5

    log_info "⑤ AI enhancement services…"
    compose up -d "${AI_SERVICES[@]}"
    sleep 5

    log_info "⑥ Metrics exporters…"
    compose_monitoring up -d "${EXPORTER_SERVICES[@]}"

    log_success "All service groups dispatched"
}

# ─────────────────────────────────────────────────────────────
# HEALTH CHECKS
# ─────────────────────────────────────────────────────────────

wait_for_services() {
    section "⏳  Waiting for Services"

    for svc in "${CORE_SERVICES[@]}";       do wait_healthy "$svc" "$TIMEOUT_SERVICES"   || true; done
    for svc in "${API_SERVICES[@]}";        do wait_healthy "$svc" "$TIMEOUT_SERVICES"   || true; done
    for svc in "${MONITORING_SERVICES[@]}"; do wait_healthy "$svc" "$TIMEOUT_MONITORING" || true; done
    for svc in "${AI_SERVICES[@]}";         do wait_healthy "$svc" "$TIMEOUT_AI"         || true; done
}

run_health_checks() {
    local json_mode=false
    [[ "${1:-}" == "--json" ]] && json_mode=true

    local results=()

    _check_endpoint() {
        local name="$1" path="$2"
        local port="${path%%/*}"
        local url="http://localhost:${path}"
        [[ "$path" == "$port" ]] && url="http://localhost:${port}"

        if curl -sf --max-time 3 "$url" &>/dev/null; then
            results+=("${name}:ok:${url}")
            [[ "$json_mode" == false ]] && echo -e "  ${GREEN}✓${NC} ${name}  ${DIM}${url}${NC}"
        else
            results+=("${name}:warn:${url}")
            [[ "$json_mode" == false ]] && echo -e "  ${YELLOW}⚠${NC} ${name}  ${DIM}${url}  (not yet reachable)${NC}"
        fi
    }

    if [[ "$json_mode" == false ]]; then
        section "🔍  Health Check"
        echo -e "${BOLD}Core APIs${NC}"
    fi

    for svc in "${API_SERVICES[@]}"; do
        [[ -v "SERVICE_PORTS[$svc]" ]] && _check_endpoint "$svc" "${SERVICE_PORTS[$svc]}"
    done

    [[ "$json_mode" == false ]] && echo -e "\n${BOLD}Monitoring${NC}"
    for svc in prometheus grafana influxdb traefik authelia; do
        [[ -v "SERVICE_PORTS[$svc]" ]] && _check_endpoint "$svc" "${SERVICE_PORTS[$svc]}"
    done

    [[ "$json_mode" == false ]] && echo -e "\n${BOLD}AI Services${NC}"
    for svc in openwebui tts-stt-service model-fine-tuning; do
        [[ -v "SERVICE_PORTS[$svc]" ]] && _check_endpoint "$svc" "${SERVICE_PORTS[$svc]}"
    done

    local ok_count=0 warn_count=0
    for r in "${results[@]}"; do
        [[ "$r" == *":ok:"*   ]] && ok_count=$(( ok_count + 1 ))
        [[ "$r" == *":warn:"* ]] && warn_count=$(( warn_count + 1 ))
    done

    if [[ "$json_mode" == true ]]; then
        echo "{"
        echo "  \"timestamp\": \"$(date -u +%FT%TZ)\","
        echo "  \"ok\": ${ok_count},"
        echo "  \"warn\": ${warn_count},"
        echo "  \"services\": ["
        local first=true
        for r in "${results[@]}"; do
            local name="${r%%:*}"; local rest="${r#*:}"; local status="${rest%%:*}"; local url="${rest#*:}"
            [[ "$first" == false ]] && echo ","
            printf '    {"name":"%s","status":"%s","url":"%s"}' "$name" "$status" "$url"
            first=false
        done
        echo ""
        echo "  ]"
        echo "}"
        return
    fi

    echo ""
    if (( warn_count == 0 )); then
        log_success "${ok_count}/${#results[@]} endpoints healthy 🎉"
    else
        log_warn "${ok_count}/${#results[@]} endpoints reachable — ${warn_count} still starting"
        log_detail "Re-check: ./${SCRIPT_NAME} status"
    fi
}

# ─────────────────────────────────────────────────────────────
# OLLAMA MODEL DOWNLOAD
# ─────────────────────────────────────────────────────────────

download_ollama_models() {
    section "🤖  AI Model Download"

    spinner_start "Waiting for Ollama daemon…"
    local elapsed=0
    while (( elapsed < TIMEOUT_OLLAMA )); do
        if docker exec "$(container_name ollama)" ollama list &>/dev/null 2>&1; then
            spinner_stop; log_success "Ollama is ready"; break
        fi
        sleep 3; elapsed=$(( elapsed + 3 ))
    done

    if (( elapsed >= TIMEOUT_OLLAMA )); then
        spinner_stop
        log_warn "Ollama did not start within ${TIMEOUT_OLLAMA}s — skipping model pull"
        log_detail "Pull later:  docker exec $(container_name ollama) ollama pull <model>"
        return 0
    fi

    local auto_pull; auto_pull="$(_env_get OLLAMA_AUTOMATIC_PULL)"
    if [[ "${auto_pull:-true}" != "true" ]]; then
        log_info "OLLAMA_AUTOMATIC_PULL=false — skipping"
        return 0
    fi

    local model_list; model_list="$(_env_get OLLAMA_MODELS)"
    model_list="${model_list:-llama3.2,nomic-embed-text}"

    IFS=',' read -ra models <<< "$model_list"
    log_info "Pulling ${#models[@]} model(s): ${models[*]}"

    local success=0
    for model in "${models[@]}"; do
        model="$(echo "$model" | xargs)"
        [[ -z "$model" ]] && continue

        spinner_start "Pulling ${model}…"
        if run timeout 300 docker exec "$(container_name ollama)" ollama pull "$model" &>/dev/null 2>&1; then
            spinner_stop; log_success "${model}"
            success=$(( success + 1 ))
        else
            spinner_stop; log_warn "${model} — failed or timed out"
        fi
    done

    local installed
    installed="$(docker exec "$(container_name ollama)" ollama list 2>/dev/null | tail -n +2 | wc -l | xargs || echo 0)"
    log_success "${installed} model(s) available"
    docker exec "$(container_name ollama)" ollama list 2>/dev/null | tail -n +2 \
        | while IFS= read -r line; do log_detail "$line"; done
}

# ─────────────────────────────────────────────────────────────
# MIGRATE
# ─────────────────────────────────────────────────────────────

cmd_migrate() {
    local target="${1:-head}"
    section "🗄  Database Migration  (target: ${target})"

    if ! container_running postgres; then
        log_error "PostgreSQL is not running. Start services first."
        exit 1
    fi

    local -a migration_services=(api-gateway marketplace plugin-registry rag-pipeline model-management)

    for svc in "${migration_services[@]}"; do
        if container_running "$svc"; then
            log_info "Running migrations in ${svc}…"
            if run docker exec "$(container_name "$svc")" \
                   alembic upgrade "$target" 2>&1 | tee -a "$LOG_FILE"; then
                log_success "${svc} — migrations applied"
            else
                log_warn "${svc} — migration failed (check logs)"
            fi
        else
            log_detail "${svc} — not running, skipping"
        fi
    done

    log_success "Migration run complete"
}

# ─────────────────────────────────────────────────────────────
# BACKUP
# ─────────────────────────────────────────────────────────────

cmd_backup() {
    local ts; ts="$(date +%Y%m%d-%H%M%S)"
    local dest="${BACKUP_DIR}/minder-${ts}"
    mkdir -p "$dest"

    section "💾  Platform Backup  →  ${dest}"

    if [[ -f "$ENV_FILE" ]]; then
        cp "$ENV_FILE" "${dest}/env.backup"
        chmod 600 "${dest}/env.backup"
        log_success ".env backed up"
    else
        log_warn ".env not found"
    fi

    if container_running postgres; then
        spinner_start "Dumping PostgreSQL…"
        if docker exec "$(container_name postgres)" \
               pg_dumpall -U minder 2>/dev/null > "${dest}/postgres.sql"; then
            spinner_stop
            log_success "PostgreSQL  ($(du -sh "${dest}/postgres.sql" | cut -f1))"
        else
            spinner_stop; log_warn "PostgreSQL dump failed"
        fi
    else
        log_warn "PostgreSQL not running — skipped"
    fi

    if container_running neo4j; then
        spinner_start "Dumping Neo4j…"
        local neo4j_dump="${dest}/neo4j.dump"
        if run docker exec "$(container_name neo4j)" \
               neo4j-admin database dump neo4j \
               --to-stdout 2>/dev/null > "$neo4j_dump"; then
            spinner_stop
            log_success "Neo4j  ($(du -sh "$neo4j_dump" | cut -f1))"
        else
            spinner_stop; log_warn "Neo4j dump failed"
        fi
    else
        log_warn "Neo4j not running — skipped"
    fi

    if container_running influxdb; then
        spinner_start "Backing up InfluxDB…"
        local influx_token; influx_token="$(_env_get INFLUXDB_ADMIN_TOKEN)"
        if [[ -n "$influx_token" ]]; then
            if run docker exec "$(container_name influxdb)" \
                   influx backup /tmp/influx-backup \
                   --token "$influx_token" &>/dev/null 2>&1; then
                run docker cp "$(container_name influxdb):/tmp/influx-backup" "${dest}/influxdb/"
                spinner_stop; log_success "InfluxDB backed up"
            else
                spinner_stop; log_warn "InfluxDB backup failed"
            fi
        else
            spinner_stop; log_warn "INFLUXDB_ADMIN_TOKEN not set — skipping InfluxDB backup"
        fi
    else
        log_warn "InfluxDB not running — skipped"
    fi

    if container_running qdrant; then
        spinner_start "Snapshotting Qdrant storage…"
        if run docker exec "$(container_name qdrant)" \
               tar czf /tmp/qdrant-backup.tar.gz /qdrant/storage 2>/dev/null && \
           run docker cp "$(container_name qdrant):/tmp/qdrant-backup.tar.gz" \
               "${dest}/qdrant.tar.gz"; then
            spinner_stop
            log_success "Qdrant  ($(du -sh "${dest}/qdrant.tar.gz" | cut -f1))"
        else
            spinner_stop; log_warn "Qdrant snapshot failed"
        fi
    else
        log_warn "Qdrant not running — skipped"
    fi

    spinner_start "Compressing backup archive…"
    local archive="${BACKUP_DIR}/minder-${ts}.tar.gz"
    if tar czf "$archive" -C "$BACKUP_DIR" "minder-${ts}" 2>/dev/null; then
        rm -rf "$dest"
        spinner_stop
        log_success "Archive: ${archive}  ($(du -sh "$archive" | cut -f1))"
    else
        spinner_stop
        log_warn "Compression failed — uncompressed backup kept at ${dest}"
    fi

    local count
    count="$(find "$BACKUP_DIR" -maxdepth 1 -name 'minder-*.tar.gz' | wc -l | xargs)"
    if (( count > 7 )); then
        find "$BACKUP_DIR" -maxdepth 1 -name 'minder-*.tar.gz' \
            | sort | head -n $(( count - 7 )) \
            | xargs rm -f
        log_detail "Pruned old backups (keeping last 7)"
    fi

    log_success "Backup complete"
}

# ─────────────────────────────────────────────────────────────
# RESTORE
# ─────────────────────────────────────────────────────────────

cmd_restore() {
    local archive="${1:-}"

    if [[ -z "$archive" ]]; then
        echo -e "\n${BOLD}Available backups:${NC}"
        local i=0
        local -a backup_files=()
        while IFS= read -r f; do
            i=$(( i + 1 ))
            backup_files+=("$f")
            local size; size="$(du -sh "$f" | cut -f1)"
            local ts; ts="$(basename "$f" .tar.gz | sed 's/minder-//')"
            printf "  ${CYAN}[%d]${NC}  %s  ${DIM}%s${NC}\n" "$i" "$ts" "$size"
        done < <(find "$BACKUP_DIR" -maxdepth 1 -name 'minder-*.tar.gz' | sort -r)

        if (( i == 0 )); then
            log_error "No backups found in ${BACKUP_DIR}"
            exit 1
        fi

        if [[ "$INTERACTIVE" == "true" ]]; then
            printf "\nSelect backup [1-%d]: " "$i"
            read -r choice
            archive="${backup_files[$(( choice - 1 ))]}"
        else
            log_error "No backup archive specified. Usage: ./${SCRIPT_NAME} restore <archive.tar.gz>"
            exit 1
        fi
    fi

    [[ ! -f "$archive" ]] && { log_error "File not found: ${archive}"; exit 1; }

    section "♻️   Restore  ←  $(basename "$archive")"
    log_warn "This will OVERWRITE current data. Services must be stopped."

    if [[ "$INTERACTIVE" == "true" ]]; then
        printf "Continue? [y/N] "
        read -r confirm
        [[ "${confirm,,}" != "y" ]] && { log_info "Restore cancelled."; return 0; }
    fi

    local tmp_dir; tmp_dir="$(mktemp -d)"
    spinner_start "Extracting archive…"
    tar xzf "$archive" -C "$tmp_dir"
    spinner_stop
    local restore_dir; restore_dir="$(find "$tmp_dir" -mindepth 1 -maxdepth 1 -type d | head -1)"

    if [[ -f "${restore_dir}/env.backup" ]]; then
        cp "${restore_dir}/env.backup" "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        log_success ".env restored"
    fi

    if ! container_running postgres; then
        compose up -d postgres
        wait_postgres_ready
    fi

    if [[ -f "${restore_dir}/postgres.sql" ]]; then
        spinner_start "Restoring PostgreSQL…"
        if docker exec -i "$(container_name postgres)" \
               psql -U minder -f - < "${restore_dir}/postgres.sql" &>/dev/null 2>&1; then
            spinner_stop; log_success "PostgreSQL restored"
        else
            spinner_stop; log_warn "PostgreSQL restore had errors (partial restore possible)"
        fi
    fi

    if [[ -f "${restore_dir}/qdrant.tar.gz" ]] && container_running qdrant; then
        spinner_start "Restoring Qdrant…"
        docker cp "${restore_dir}/qdrant.tar.gz" "$(container_name qdrant):/tmp/"
        docker exec "$(container_name qdrant)" \
            tar xzf /tmp/qdrant-backup.tar.gz -C / 2>/dev/null
        spinner_stop; log_success "Qdrant restored"
    fi

    rm -rf "$tmp_dir"
    log_success "Restore complete — restart services: ./${SCRIPT_NAME} start"
}

# ─────────────────────────────────────────────────────────────
# DOCTOR  — deep diagnostics  (now includes version drift)
# ─────────────────────────────────────────────────────────────

cmd_doctor() {
    section "🩺  System Diagnostics"

    local issues=0

    echo -e "${BOLD}Docker${NC}"
    log_detail "Version: $(docker --version)"
    log_detail "Compose: $(docker compose version --short 2>/dev/null || echo 'n/a')"

    local docker_mem
    docker_mem="$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)"
    local docker_mem_gb=$(( docker_mem / 1073741824 ))
    if (( docker_mem_gb < 4 )); then
        log_warn "Docker has only ${docker_mem_gb}GB RAM (recommend ≥4GB for Ollama)"
        issues=$(( issues + 1 ))
    else
        log_detail "Docker RAM: ${docker_mem_gb}GB ✓"
    fi

    echo -e "\n${BOLD}Disk${NC}"
    local free_gb
    free_gb="$(df -BG "$SCRIPT_DIR" 2>/dev/null | awk 'NR==2{gsub("G",""); print $4}' || echo 999)"
    if (( free_gb < 10 )); then
        log_warn "Low disk space: ${free_gb}GB free"
        issues=$(( issues + 1 ))
    else
        log_detail "Free space: ${free_gb}GB ✓"
    fi

    echo -e "\n${BOLD}Environment (.env)${NC}"
    if [[ ! -f "$ENV_FILE" ]]; then
        log_warn ".env not found — run install first"
        issues=$(( issues + 1 ))
    else
        local perm; perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%A' "$ENV_FILE" 2>/dev/null || echo '???')"
        if [[ "$perm" != "600" ]] && [[ "$perm" != "0600" ]]; then
            log_warn ".env permissions are ${perm} — should be 600"
            issues=$(( issues + 1 ))
        else
            log_detail "Permissions: ${perm} ✓"
        fi

        local weak=0
        while IFS='=' read -r key val; do
            [[ "$key" =~ ^#  ]] && continue
            [[ -z "$val"     ]] && continue
            if [[ "$val" =~ ^(admin|password|secret|changeme|replace_me|minder)$ ]]; then
                log_warn "Weak value detected for ${key}"
                weak=$(( weak + 1 ))
                issues=$(( issues + 1 ))
            fi
        done < "$ENV_FILE"
        (( weak == 0 )) && log_detail "No obvious weak secrets ✓"
    fi

    echo -e "\n${BOLD}Port Availability${NC}"
    local -a ports=(5432 6379 8000 8001 8002 8003 8004 8005 8006 8007 8080 8081 8086 9090 9091 3000)
    for port in "${ports[@]}"; do
        if 2>/dev/null >/dev/tcp/127.0.0.1/"$port"; then
            if docker ps --format '{{.Ports}}' 2>/dev/null | grep -q ":${port}->"; then
                log_detail ":${port} — in use by Minder ✓"
            else
                log_warn ":${port} — in use by another process"
                issues=$(( issues + 1 ))
            fi
        else
            log_detail ":${port} — free ✓"
        fi
    done

    echo -e "\n${BOLD}Container Health${NC}"
    local unhealthy_containers
    unhealthy_containers="$(docker ps --filter 'health=unhealthy' \
        --format '{{.Names}}' 2>/dev/null | grep "^${CONTAINER_PREFIX}-" || true)"
    if [[ -n "$unhealthy_containers" ]]; then
        log_warn "Unhealthy containers:"
        echo "$unhealthy_containers" | while IFS= read -r c; do log_detail "  $c"; done
        issues=$(( issues + 1 ))
    else
        local running
        running="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
        log_detail "${running} containers running, none unhealthy ✓"
    fi

    echo -e "\n${BOLD}Docker Volumes${NC}"
    local dangling_volumes
    dangling_volumes="$(docker volume ls -q --filter dangling=true 2>/dev/null | wc -l | xargs)"
    if (( dangling_volumes > 5 )); then
        log_warn "${dangling_volumes} dangling volumes (run: docker volume prune)"
    else
        log_detail "Dangling volumes: ${dangling_volumes} ✓"
    fi

    # ── Version drift check ──────────────────────────────────
    echo -e "\n${BOLD}Image Version Drift${NC}"
    if [[ "$SKIP_VERSION_CHECK" == "true" ]]; then
        log_warn "Version check skipped (curl unavailable or SKIP_VERSION_CHECK=1)"
    else
        log_info "Querying registries for newer compatible versions…"
        version_drift_report false
        # Count drift as issues
        local drift_count
        drift_count="$(version_drift_report false 2>/dev/null | grep -c '→\|AVAILABLE' || echo 0)"
        (( drift_count > 0 )) && issues=$(( issues + 1 )) || true
    fi

    echo ""
    if (( issues == 0 )); then
        log_success "No issues found — system looks healthy 🎉"
    else
        log_warn "${issues} issue(s) found — review warnings above"
    fi
}

# ─────────────────────────────────────────────────────────────
# UPDATE  — pull latest compatible images, rebuild, rolling restart
# ─────────────────────────────────────────────────────────────

cmd_update() {
    local check_only=false
    [[ "${1:-}" == "--check" ]] && check_only=true

    if [[ "$check_only" == "true" ]]; then
        section "🔍  Update Check  (no changes will be made)"
        log_info "Querying registries…"
        version_drift_report false
        return 0
    fi

    section "🔄  Update Platform"

    # Pull with smart version resolution
    pull_all_images

    log_info "Rebuilding custom Minder images…"
    run compose build --pull --no-cache 2>&1 | tee -a "$LOG_FILE" | grep -E 'Step|Successfully|ERROR' || true

    log_info "Performing rolling restart…"
    for svc in "${SECURITY_SERVICES[@]}" "${CORE_SERVICES[@]}" "${API_SERVICES[@]}" \
               "${MONITORING_SERVICES[@]}" "${AI_SERVICES[@]}"; do
        if container_running "$svc"; then
            run compose up -d --no-deps "$svc"
            log_detail "${svc} restarted"
            sleep 2
        fi
    done

    log_success "Update complete — run './${SCRIPT_NAME} status' to verify"
}

# ─────────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────────

cmd_status() {
    local json_mode=false
    [[ "${1:-}" == "--json" ]] && json_mode=true

    if [[ "$json_mode" == true ]]; then
        run_health_checks --json
        return
    fi

    section "📊  Minder Platform Status"

    local total healthy unhealthy starting
    total="$(    docker ps --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
    healthy="$(  docker ps --filter 'health=healthy'   --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
    unhealthy="$(docker ps --filter 'health=unhealthy' --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"
    starting="$( docker ps --filter 'health=starting'  --format '{{.Names}}' 2>/dev/null | grep -c "^${CONTAINER_PREFIX}-" || echo 0)"

    echo -e "${BOLD}Summary${NC}  total=${total}  ${GREEN}healthy=${healthy}${NC}  ${YELLOW}starting=${starting}${NC}  ${RED}unhealthy=${unhealthy}${NC}"
    echo ""

    echo -e "${BOLD}Containers${NC}"
    docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null \
        | grep -E "NAMES|${CONTAINER_PREFIX}-" | head -30

    echo ""
    echo -e "${BOLD}Resource Usage${NC}"
    docker stats --no-stream \
        --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" 2>/dev/null \
        | grep -E "NAME|${CONTAINER_PREFIX}-" | head -20

    echo ""
    run_health_checks
}

# ─────────────────────────────────────────────────────────────
# STOP
# ─────────────────────────────────────────────────────────────

cmd_stop() {
    log_step "Stopping all services"

    compose_monitoring down

    if docker network ls --format '{{.Name}}' | grep -q "^${NETWORK_NAME}$"; then
        run docker network rm "$NETWORK_NAME" 2>/dev/null \
            && log_success "Network '${NETWORK_NAME}' removed" \
            || log_warn "Network not removed (may still be in use)"
    fi

    if [[ "$CLEAN_DANGLING" == "true" ]]; then
        local reclaimed
        reclaimed="$(docker image prune -f | grep 'Total reclaimed' || echo 'unknown')"
        log_success "Dangling images pruned — ${reclaimed}"
    fi

    log_success "All services stopped"
}

# ─────────────────────────────────────────────────────────────
# START / RESTART
# ─────────────────────────────────────────────────────────────

cmd_start() {
    check_prerequisites
    create_networks
    start_services
    wait_for_services
    run_health_checks
}

cmd_restart() {
    cmd_stop
    sleep 3
    cmd_start
}

# ─────────────────────────────────────────────────────────────
# UNINSTALL
# ─────────────────────────────────────────────────────────────

cmd_uninstall() {
    local purge=false
    [[ "${1:-}" == "--purge" ]] && purge=true

    if [[ "$purge" == true ]]; then
        echo -e "${RED}${BOLD}"
        echo "  ┌─────────────────────────────────────────────────────┐"
        echo "  │  ⚠  DESTRUCTIVE OPERATION — CANNOT BE UNDONE  ⚠    │"
        echo "  │  All services AND data volumes will be deleted.     │"
        echo "  └─────────────────────────────────────────────────────┘"
        echo -e "${NC}"

        if [[ "$INTERACTIVE" == "true" ]]; then
            printf "Type ${BOLD}DELETE${NC} to confirm: "
            read -r confirm
            [[ "$confirm" != "DELETE" ]] && { log_info "Uninstall cancelled."; return 0; }
        fi

        log_warn "Removing all services, networks, and volumes…"
        compose_monitoring down -v --remove-orphans
        log_success "Full uninstall complete"
    else
        log_info "Stopping services (data volumes are preserved)"
        compose_monitoring down
        log_success "Services stopped — data preserved"
        log_detail "To also delete data: ./${SCRIPT_NAME} uninstall --purge"
    fi
}

# ─────────────────────────────────────────────────────────────
# LOGS
# ─────────────────────────────────────────────────────────────

cmd_logs() {
    local service="${1:-}" lines="${2:-100}"

    if [[ -n "$service" ]]; then
        local cname; cname="$(container_name "$service")"
        if docker ps --format '{{.Names}}' | grep -q "^${cname}$"; then
            log_info "Streaming ${service} logs (Ctrl+C to exit)…"
            docker logs -f --tail "$lines" "$cname"
        else
            log_error "No running container: ${cname}"
            log_detail "Running containers:"
            docker ps --format '  {{.Names}}' | grep "^  ${CONTAINER_PREFIX}-" || echo "  (none)"
            return 1
        fi
    else
        log_info "Streaming all service logs (Ctrl+C to exit)…"
        compose logs -f --tail 50
    fi
}

# ─────────────────────────────────────────────────────────────
# SHELL
# ─────────────────────────────────────────────────────────────

cmd_shell() {
    local service="${1:-}"

    if [[ -z "$service" ]]; then
        echo -e "${BOLD}Running containers:${NC}"
        docker ps --format '  {{.Names}}' | grep "^  ${CONTAINER_PREFIX}-" \
            | sed "s/  ${CONTAINER_PREFIX}-/  /" || echo "  (none)"
        echo ""
        if [[ "$INTERACTIVE" == "true" ]]; then
            printf "Container name (without '${CONTAINER_PREFIX}-'): "
            read -r service
        else
            log_error "Specify a service: ./${SCRIPT_NAME} shell <service>"
            exit 1
        fi
    fi

    local cname; cname="$(container_name "$service")"
    if ! docker ps --format '{{.Names}}' | grep -q "^${cname}$"; then
        log_error "Container not running: ${cname}"
        exit 1
    fi

    local shell="bash"
    docker exec -it "$cname" bash --version &>/dev/null || shell="sh"

    log_info "Opening ${shell} in ${cname}  (exit to return)"
    docker exec -it "$cname" "$shell"
}

# ─────────────────────────────────────────────────────────────
# SUCCESS BANNER
# ─────────────────────────────────────────────────────────────

print_success_banner() {
    echo ""
    echo -e "${BOLD}${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BOLD}${GREEN}║${NC}         ${BOLD}🎉  Minder Platform v${SCRIPT_VERSION} — Ready!  🎉${NC}          ${BOLD}${GREEN}║${NC}"
    echo -e "${BOLD}${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    echo -e "${BOLD}${MAGENTA}🔐 Security${NC}"
    echo -e "   Traefik Dashboard  →  ${CYAN}http://localhost:8081${NC}"
    echo -e "   Authelia Portal    →  ${CYAN}http://localhost:9091${NC}"
    echo -e "   ${YELLOW}Default users: admin/admin123, developer/admin123, user/admin123${NC}"
    echo -e "   ${RED}⚠️  Change default passwords immediately!${NC}"

    echo ""
    echo -e "${BOLD}${MAGENTA}📍 Core APIs${NC}"
    local api_names=("API Gateway" "Plugin Registry" "Marketplace" "State Manager" "RAG Pipeline" "Model Mgmt")
    local api_ports=(8000       8001              8002          8003             8004           8005)
    for i in "${!api_names[@]}"; do
        printf "   %-20s →  ${CYAN}http://localhost:%s${NC}\n" "${api_names[$i]}" "${api_ports[$i]}"
    done

    echo ""
    echo -e "${BOLD}${MAGENTA}🤖 AI Services${NC}"
    echo -e "   OpenWebUI           →  ${CYAN}http://localhost:8080${NC}"
    echo -e "   TTS / STT           →  ${CYAN}http://localhost:8006${NC}"
    echo -e "   Model Fine-tuning   →  ${CYAN}http://localhost:8007${NC}"

    echo ""
    echo -e "${BOLD}${MAGENTA}📊 Monitoring${NC}"
    echo -e "   Prometheus          →  ${CYAN}http://localhost:9090${NC}"
    echo -e "   Grafana             →  ${CYAN}http://localhost:3000${NC}"
    echo -e "   InfluxDB            →  ${CYAN}http://localhost:8086${NC}"

    echo ""
    echo -e "${BOLD}${MAGENTA}🔧 Commands${NC}"
    echo -e "   ${DIM}./${SCRIPT_NAME} status              ${NC}— health overview"
    echo -e "   ${DIM}./${SCRIPT_NAME} status --json       ${NC}— machine-readable health"
    echo -e "   ${DIM}./${SCRIPT_NAME} logs [service]      ${NC}— tail logs"
    echo -e "   ${DIM}./${SCRIPT_NAME} shell [service]     ${NC}— open container shell"
    echo -e "   ${DIM}./${SCRIPT_NAME} migrate             ${NC}— run DB migrations"
    echo -e "   ${DIM}./${SCRIPT_NAME} backup              ${NC}— full platform backup"
    echo -e "   ${DIM}./${SCRIPT_NAME} restore             ${NC}— restore from backup"
    echo -e "   ${DIM}./${SCRIPT_NAME} doctor              ${NC}— deep diagnostics + version drift"
    echo -e "   ${DIM}./${SCRIPT_NAME} update              ${NC}— smart pull + rolling restart"
    echo -e "   ${DIM}./${SCRIPT_NAME} update --check      ${NC}— check for updates (no changes)"
    echo -e "   ${DIM}./${SCRIPT_NAME} stop                ${NC}— stop all services"
    echo -e "   ${DIM}./${SCRIPT_NAME} uninstall --purge   ${NC}— remove everything"
    echo ""
    echo -e "${DIM}Log file: ${LOG_FILE}${NC}"
    echo ""
}

# ─────────────────────────────────────────────────────────────
# HELP
# ─────────────────────────────────────────────────────────────

show_help() {
    cat << EOF

${BOLD}Minder Platform${NC}  v${SCRIPT_VERSION}  —  Setup & Lifecycle Management

${BOLD}USAGE${NC}
    ./${SCRIPT_NAME} [command] [options]

${BOLD}INSTALL & LIFECYCLE${NC}
    (none)                  Full install: prereqs → env → network → DB → services → health
    start                   Start all services
    stop [--clean]          Stop services; --clean prunes dangling images
    restart                 Stop then start
    update                  Smart pull (latest compatible) + rebuild + rolling restart
    update --check          Show available updates without applying anything

${BOLD}OPERATIONS${NC}
    status [--json]         Health overview; --json for machine-readable output
    logs [service] [lines]  Tail logs (all or specific service)
    shell [service]         Open an interactive shell in a container
    migrate [target]        Run Alembic migrations (default: head)
    doctor                  Deep diagnostics: disk, ports, secrets, images, version drift

${BOLD}DATA MANAGEMENT${NC}
    backup                  Full backup: Postgres, Neo4j, InfluxDB, Qdrant, .env
    restore [archive]       Restore from a backup archive (interactive if no path given)
    uninstall               Stop services, preserve data volumes
    uninstall --purge       Stop and DELETE all data (irreversible)

${BOLD}VERSION RESOLUTION${NC}
    Images are pulled with "try latest compatible → fall back to pinned" logic.
    Constraints per image:
      major  — accept any newer patch/minor within same major  (e.g. postgres:16.x)
      minor  — accept newer patches only within same major.minor
      none   — accept any newer version (used for rolling-release images)
      patch  — always use exact pinned tag (no resolution attempted)

    SKIP_VERSION_CHECK=1   Bypass registry queries, use pins directly
    VERBOSE=1              Show per-image resolution details

${BOLD}FLAGS${NC}
    DRY_RUN=1               Preview commands without executing
    VERBOSE=1               Enable debug-level output
    NONINTERACTIVE=1        Disable interactive prompts (for CI)
    SKIP_VERSION_CHECK=1    Use exact pinned versions, skip registry queries

${BOLD}EXAMPLES${NC}
    ./${SCRIPT_NAME}                                # Fresh install
    ./${SCRIPT_NAME} update --check                 # What's outdated?
    ./${SCRIPT_NAME} update                         # Pull + restart (smart versioning)
    SKIP_VERSION_CHECK=1 ./${SCRIPT_NAME} update   # Force pinned versions
    ./${SCRIPT_NAME} doctor                         # Full diagnostics with drift report
    ./${SCRIPT_NAME} status --json                  # JSON health for monitoring
    DRY_RUN=1 ./${SCRIPT_NAME} update              # Preview update steps

EOF
}

# ─────────────────────────────────────────────────────────────
# FULL INSTALL
# ─────────────────────────────────────────────────────────────

cmd_install() {
    clear
    echo -e "${BOLD}${CYAN}"
    echo "  ╔══════════════════════════════════════════════════════════╗"
    echo "  ║         Minder Platform — Automated Setup               ║"
    printf "  ║                   Version %-30s║\n" "${SCRIPT_VERSION}"
    echo "  ╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo -e "${YELLOW}  ⚠  DRY RUN MODE — no changes will be made${NC}\n"
    fi

    progress_init 10   # one extra step for image resolution

    progress_next "Checking prerequisites";    check_prerequisites
    progress_next "Setting up environment";    setup_environment
    progress_next "Creating Docker network";   create_networks
    progress_next "Resolving & pulling images";pull_all_images
    progress_next "Initialising databases";    initialize_database
    progress_next "Starting services";         start_services
    progress_next "Waiting for services";      wait_for_services
    progress_next "Downloading AI models";     download_ollama_models
    progress_next "Running migrations";        cmd_migrate "head"
    progress_next "Health checks";             run_health_checks

    print_success_banner
}

# ─────────────────────────────────────────────────────────────
# ENTRYPOINT
# ─────────────────────────────────────────────────────────────

main() {
    local args=()
    for arg in "$@"; do
        case "$arg" in
            --dry-run)   DRY_RUN=true ;;
            --verbose)   VERBOSE=true ;;
            --json)      JSON_OUTPUT=true ;;
            --skip-version-check) SKIP_VERSION_CHECK=true ;;
            *)           args+=("$arg") ;;
        esac
    done

    local cmd="${args[0]:-install}"
    local arg1="${args[1]:-}"
    local arg2="${args[2]:-}"

    case "$cmd" in
        install)    cmd_install ;;
        start)      cmd_start ;;
        stop)
            [[ "$arg1" == "--clean" || "$arg1" == "--clean-dangling" ]] && CLEAN_DANGLING=true
            cmd_stop
            ;;
        restart)    cmd_restart ;;
        status)
            [[ "$arg1" == "--json" || "$JSON_OUTPUT" == true ]] \
                && cmd_status --json || cmd_status
            ;;
        logs)       cmd_logs "$arg1" "${arg2:-100}" ;;
        shell)      cmd_shell "$arg1" ;;
        migrate)    cmd_migrate "${arg1:-head}" ;;
        backup)     cmd_backup ;;
        restore)    cmd_restore "$arg1" ;;
        doctor)     cmd_doctor ;;
        update)     cmd_update "${arg1:-}" ;;
        uninstall)  cmd_uninstall "$arg1" ;;
        -h|--help|help) show_help ;;
        *)
            log_error "Unknown command: ${cmd}"
            show_help
            exit 1
            ;;
    esac
}

main "$@"