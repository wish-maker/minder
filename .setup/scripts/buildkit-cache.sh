#!/bin/bash
# ============================================================================
# Minder Platform - BuildKit Caching Implementation
# ============================================================================
# Optimizes Docker build performance with advanced caching strategies
# Usage: Source this file in setup.sh or use standalone
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
BUILD_CACHE_DIR="${PROJECT_ROOT}/.buildcache"
CACHE_METADATA_DIR="${BUILD_CACHE_DIR}/metadata"

# ============================================================================
# BuildKit Configuration
# ============================================================================

# Enable BuildKit
export DOCKER_BUILDKIT=1
export BUILDKIT_PROGRESS=plain

# Cache configuration
export BUILDKIT_CACHE_KV_REF_DIR="${BUILD_CACHE_DIR}/kv"
export BUILDKIT_CACHE_KV_REF_MAX_MB=1024

# ============================================================================
# Helper Functions
# ============================================================================

log_build_info() {
    echo -e "\033[0;34m[BuildKit]\033[0m $1"
}

log_build_success() {
    echo -e "\033[0;32m[BuildKit]\033[0m $1"
}

log_build_warn() {
    echo -e "\033[1;33m[BuildKit]\033[0m $1"
}

# ============================================================================
# Cache Management Functions
# ============================================================================

initialize_build_cache() {
    log_build_info "Initializing BuildKit cache..."

    mkdir -p "${BUILD_CACHE_DIR}"/{layers,metadata,tmp,kv}
    mkdir -p "${CACHE_METADATA_DIR}"

    # Create cache metadata file
    local metadata_file="${CACHE_METADATA_DIR}/cache-info.json"
    cat > "$metadata_file" << EOF
{
  "version": "1.0",
  "created": "$(date -Iseconds)",
  "last_cleanup": "$(date -Iseconds)",
  "total_builds": 0,
  "cache_hits": 0
}
EOF

    log_build_success "BuildKit cache initialized: ${BUILD_CACHE_DIR}"
}

calculate_source_checksum() {
    local service_dir=$1
    local dockerfile=$2

    # Calculate checksum of Dockerfile and source files
    local checksum
    checksum=$(find "$service_dir" -type f \( -name "Dockerfile" -o -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "go.mod" -o -name "*.java" \) -exec sha256sum {} \; 2>/dev/null | sort | sha256sum | cut -d' ' -f1)

    echo "$checksum"
}

get_cached_checksum() {
    local service_name=$1
    local cache_file="${CACHE_METADATA_DIR}/${service_name}.checksum"

    if [ -f "$cache_file" ]; then
        cat "$cache_file"
    fi
}

update_cache_metadata() {
    local service_name=$1
    local new_checksum=$2
    local cache_file="${CACHE_METADATA_DIR}/${service_name}.checksum"

    echo "$new_checksum" > "$cache_file"

    # Update build count
    local metadata_file="${CACHE_METADATA_DIR}/cache-info.json"
    if [ -f "$metadata_file" ]; then
        local total_builds
        total_builds=$(jq -r '.total_builds // 0' "$metadata_file")
        total_builds=$((total_builds + 1))

        jq --arg total "$total_builds" '.total_builds = $total_builds' "$metadata_file" > "${metadata_file}.tmp"
        mv "${metadata_file}.tmp" "$metadata_file"
    fi
}

is_cache_valid() {
    local service_name=$1
    local current_checksum=$2
    local cached_checksum

    cached_checksum=$(get_cached_checksum "$service_name")

    if [ "$cached_checksum" = "$current_checksum" ]; then
        return 0  # Cache hit
    else
        return 1  # Cache miss
    fi
}

# ============================================================================
# Build Functions with Caching
# ============================================================================

build_with_cache() {
    local service_name=$1
    local service_dir="${PROJECT_ROOT}/services/${service_name}"
    local dockerfile="${service_dir}/Dockerfile"

    if [ ! -d "$service_dir" ]; then
        log_build_warn "Service directory not found: ${service_dir}"
        return 1
    fi

    if [ ! -f "$dockerfile" ]; then
        log_build_warn "Dockerfile not found: ${dockerfile}"
        return 1
    fi

    log_build_info "Building ${service_name} with BuildKit caching..."

    # Calculate current checksum
    local current_checksum
    current_checksum=$(calculate_source_checksum "$service_dir")

    # Check if cache is valid
    if is_cache_valid "$service_name" "$current_checksum"; then
        log_build_success "Cache HIT for ${service_name} - using cached layers"
        return 0
    else
        log_build_info "Cache MISS for ${service_name} - building with cache mount"
    fi

    # Build with BuildKit cache mount
    local build_cmd="docker build"
    build_cmd+=" --file '${dockerfile}'"
    build_cmd+=" --tag 'minder/${service_name}:latest'"
    build_cmd+=" --tag 'minder/${service_name}:cached'"
    build_cmd+=" --cache-from 'type=local,src=${BUILD_CACHE_DIR}/layers'"
    build_cmd+=" --cache-to 'type=local,dest=${BUILD_CACHE_DIR}/layers,mode=max'"
    build_cmd+=" --build-arg 'BUILDKIT_INLINE_CACHE=1'"
    build_cmd+=" '${service_dir}'"

    # Execute build
    eval "$build_cmd"

    # Update cache metadata
    update_cache_metadata "$service_name" "$current_checksum"

    log_build_success "${service_name} build completed with caching"
}

# ============================================================================
# Cache Maintenance Functions
# ============================================================================

cleanup_build_cache() {
    local max_size_mb=${1:-1024}
    local max_age_days=${2:-30}

    log_build_info "Cleaning up build cache..."

    # Remove old temporary files
    find "${BUILD_CACHE_DIR}/tmp" -type f -mtime +1 -delete 2>/dev/null || true

    # Clean old metadata
    find "${CACHE_METADATA_DIR}" -type f -name "*.checksum" -mtime +${max_age_days} -delete 2>/dev/null || true

    # Prune Docker build cache
    docker builder prune -f --filter "until=${max_age_days}d" > /dev/null 2>&1 || true

    # Update metadata
    local metadata_file="${CACHE_METADATA_DIR}/cache-info.json"
    if [ -f "$metadata_file" ]; then
        jq --arg cleanup "$(date -Iseconds)" '.last_cleanup = $cleanup' "$metadata_file" > "${metadata_file}.tmp"
        mv "${metadata_file}.tmp" "$metadata_file"
    fi

    log_build_success "Build cache cleanup completed"
}

get_cache_stats() {
    log_build_info "Build cache statistics..."

    local metadata_file="${CACHE_METADATA_DIR}/cache-info.json"
    if [ -f "$metadata_file" ]; then
        echo "Cache Metadata:"
        jq '.' "$metadata_file"
    fi

    echo ""
    echo "Cache Directory Size:"
    du -sh "${BUILD_CACHE_DIR}" 2>/dev/null || echo "Cache directory not found"

    echo ""
    echo "Cached Services:"
    find "${CACHE_METADATA_DIR}" -name "*.checksum" -exec basename {} .checksum \; 2>/dev/null | sort || echo "No cached services"
}

# ============================================================================
# Standalone Usage
# ============================================================================

case "${1:-}" in
    init)
        initialize_build_cache
        ;;
    build)
        if [ -z "${2:-}" ]; then
            echo "Usage: $0 build <service-name>"
            exit 1
        fi
        build_with_cache "$2"
        ;;
    cleanup)
        cleanup_build_cache "${2:-1024}" "${3:-30}"
        ;;
    stats)
        get_cache_stats
        ;;
    *)
        echo "Minder Platform - BuildKit Cache Management"
        echo ""
        echo "Usage: $0 <command> [options]"
        echo ""
        echo "Commands:"
        echo "  init                  Initialize BuildKit cache directory"
        echo "  build <service>       Build specific service with caching"
        echo "  cleanup [size_mb] [days]  Clean up old cache entries"
        echo "  stats                 Show cache statistics"
        echo ""
        echo "Examples:"
        echo "  $0 init"
        echo "  $0 build api-gateway"
        echo "  $0 cleanup 512 7"
        echo "  $0 stats"
        exit 1
        ;;
esac
