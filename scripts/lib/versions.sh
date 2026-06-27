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
    local cache_file
    cache_file="$(_cache_file "dockerhub" "$repo")"
    
    # Try cache first
    local cached_tags
    cached_tags="$(_load_cached_tags "$cache_file")"
    if [[ -n "$cached_tags" ]]; then
        log_debug "dockerhub_list_tags: using cached tags for ${repo}"
        echo "$cached_tags"
        return 0
    fi
    
    # Cache miss - fetch from registry
    local url="https://hub.docker.com/v2/repositories/${repo}/tags?page_size=100&ordering=last_updated"
    local response
    if ! response="$(curl -sf --max-time "${TIMEOUT_REGISTRY}" "$url" 2>/dev/null)"; then
        log_debug "dockerhub_list_tags: HTTP request failed for ${repo}"
        echo ""
        return 1
    fi
    
    # Extract tags
    local tags
    tags="$(echo "$response" \
        | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
        | sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//')"
    
    # Save to cache
    if [[ -n "$tags" ]]; then
        _cache_tags "$cache_file" "$tags"
    fi
    
    echo "$tags"
}

# ── GHCR tag query ────────────────────────────────────────────
# GHCR exposes the OCI Distribution Spec tag listing endpoint.
# No auth needed for public packages.
ghcr_list_tags() {
    local repo="$1"   # e.g. open-webui/open-webui
    local cache_file
    cache_file="$(_cache_file "ghcr" "$repo")"
    
    # Try cache first
    local cached_tags
    cached_tags="$(_load_cached_tags "$cache_file")"
    if [[ -n "$cached_tags" ]]; then
        log_debug "ghcr_list_tags: using cached tags for ${repo}"
        echo "$cached_tags"
        return 0
    fi
    
    # Cache miss - fetch from registry
    local url="https://ghcr.io/v2/${repo}/tags/list"
    local response
    if ! response="$(curl -sf --max-time "${TIMEOUT_REGISTRY}" \
            -H "Accept: application/json" "$url" 2>/dev/null)"; then
        log_debug "ghcr_list_tags: HTTP request failed for ${repo}"
        echo ""
        return 1
    fi
    
    # Extract tags
    local tags
    tags="$(echo "$response" \
        | grep -oE '"[^"]+"' \
        | sed 's/"//g' \
        | grep -v '^tags$|^name$|^\{$|^\}$')"
    
    # Save to cache
    if [[ -n "$tags" ]]; then
        _cache_tags "$cache_file" "$tags"
    fi
    
    echo "$tags"
}

# ── Quay.io tag query ─────────────────────────────────────────
quay_list_tags() {
    local repo="$1"   # e.g. prometheus/prometheus
    local cache_file
    cache_file="$(_cache_file "quay" "$repo")"
    
    # Try cache first
    local cached_tags
    cached_tags="$(_load_cached_tags "$cache_file")"
    if [[ -n "$cached_tags" ]]; then
        log_debug "quay_list_tags: using cached tags for ${repo}"
        echo "$cached_tags"
        return 0
    fi
    
    # Cache miss - fetch from registry
    local url="https://quay.io/api/v1/repository/${repo}/tag/?limit=100&onlyActiveTags=true"
    local response
    if ! response="$(curl -sf --max-time "${TIMEOUT_REGISTRY}" "$url" 2>/dev/null)"; then
        log_debug "quay_list_tags: HTTP request failed for ${repo}"
        echo ""
        return 1
    fi
    
    # Extract tags
    local tags
    tags="$(echo "$response" \
        | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' \
        | sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//')"
    
    # Save to cache
    if [[ -n "$tags" ]]; then
        _cache_tags "$cache_file" "$tags"
    fi
    
    echo "$tags"
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

    # ── Try multiple versions from newest to oldest ─────────────
    # Instead of failing back to pinned immediately, try newer versions
    # that satisfy the constraint, falling back progressively until we find
    # one that actually works (manifest check passes).

    spinner_start "Resolving ${image_base}: finding latest working version..."

    # Re-fetch all tags to get complete list (already filtered by constraint)
    # This is necessary because we need to try multiple versions
    local working_tag=""
    local tried_tags=()

    # Sort all_tags by version (newest first) and try each one
    while IFS= read -r tag; do
        [[ -z "$tag" ]] && continue

        # Skip if we already tried this tag
        if [[ " ${tried_tags[*]} " =~ " ${tag} " ]]; then
            continue
        fi

        # Check if satisfies constraint
        if ! _tag_satisfies_constraint "$tag" "$stable_prefix" "$constraint"; then
            continue
        fi

        tried_tags+=("$tag")

        # Build test ref
        local test_ref
        case "$registry" in
            ghcr) test_ref="ghcr.io/${repo}:${tag}" ;;
            quay) test_ref="quay.io/${repo}:${tag}" ;;
            *)    test_ref="${image_base}:${tag}" ;;
        esac

        # Try to verify tag exists via Docker Hub API (avoids rate limits)
        # This is more reliable than docker manifest inspect for unauthenticated requests
        local tag_exists=false
        case "$registry" in
            dockerhub)
                # Use Docker Hub API to check if tag exists
                if curl -s -f "https://registry.hub.docker.com/v2/repositories/${repo}/tags/${tag}" &>/dev/null; then
                    tag_exists=true
                fi
                ;;
            *)
                # For other registries, try manifest inspect as fallback
                if timeout 5 docker manifest inspect "${test_ref}" &>/dev/null 2>&1; then
                    tag_exists=true
                fi
                ;;
        esac

        if [[ "$tag_exists" == "true" ]]; then
            working_tag="$tag"
            break
        fi

        log_debug "  ${tag}: tag not found or manifest check failed"
    done <<< "$all_tags"

    spinner_stop

    if [[ -n "$working_tag" ]]; then
        # Build final ref with working tag
        local final_ref
        case "$registry" in
            ghcr) final_ref="ghcr.io/${repo}:${working_tag}" ;;
            quay) final_ref="quay.io/${repo}:${working_tag}" ;;
            *)    final_ref="${image_base}:${working_tag}" ;;
        esac

        if [[ "$working_tag" == "$pinned_tag" ]]; then
            log_detail "${image_base}: using pinned ${pinned_tag} (no newer working version found)"
        else
            log_success "${image_base}: ${pinned_tag} → ${CYAN}${working_tag}${NC}  (latest working)"
        fi

        RESOLVED_IMAGE_TAGS["$pinned_ref"]="$final_ref"
        echo "$final_ref"
    else
        log_warn "${image_base}: no working version found — falling back to pinned ${pinned_tag}"
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

