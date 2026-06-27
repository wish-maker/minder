# ─────────────────────────────────────────────────────────────
# TAG CACHE FUNCTIONS
# ─────────────────────────────────────────────────────────────

# Cache directory for tag lists
# Cache constants (already defined at top of script)
# CACHE_DIR, TAGS_CACHE_DIR, and CACHE_TTL_HOURS are readonly globals

# Get cache file path for a registry/repo
_cache_file() {
    local registry="$1"  # dockerhub, ghcr, quay
    local repo="$2"       # library/postgres, open-webui/open-webui
    local safe_repo
    safe_repo="${repo//\//--}"  # Replace / with --
    echo "${CACHE_DIR}/${registry}/${safe_repo}.json"
}

# Check if cache file exists and is not expired
_cache_expired() {
    local cache_file="$1"
    local now
    now="$(date +%s)"
    
    # If cache doesn't exist, it's expired
    [[ ! -f "$cache_file" ]] && return 0
    
    # Check cache age
    local cache_time cache_age
    cache_time="$(stat -c %Y "$cache_file" 2>/dev/null || echo 0)"
    cache_age=$((now - cache_time))
    
    # Cache expired if older than TTL
    [[ $cache_age -gt $CACHE_TTL ]]
}

# Load cached tags from disk
_load_cached_tags() {
    local cache_file="$1"
    
    # Return empty if cache expired or doesn't exist
    if _cache_expired "$cache_file"; then
        echo ""
        return 1
    fi
    
    # Extract tags array from JSON cache
    if [[ -f "$cache_file" ]]; then
        grep -oE '"tags"[[:space:]]*:[[:space:]]*\[[^]]+\]' "$cache_file" 2>/dev/null | \
            sed 's/"tags"[[:space:]]*:[[:space:]]*\[//;s/\]$//;s/"//g;s/,/\n/g' | \
            grep -v '^$' || echo ""
    else
        echo ""
    fi
}

# Save tags to cache
_cache_tags() {
    local cache_file="$1"
    local tags="$2"
    local cache_dir
    cache_dir="$(dirname "$cache_file")"
    
    # Create cache directory if needed
    mkdir -p "$cache_dir"
    
    # Save tags with timestamp
    local timestamp
    timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    
    cat > "$cache_file" << CACHE_EOF
{
  "timestamp": "${timestamp}",
  "tags": [
$(echo "$tags" | sed 's/^/    "/;s/$/",/' | sed '$ s/,$//')
  ]
}
CACHE_EOF
    
    log_debug "Cached tags to ${cache_file}"
}
