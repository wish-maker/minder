# ─────────────────────────────────────────────────────────────
# COMPOSE FILE MANAGEMENT
# ─────────────────────────────────────────────────────────────

should_regenerate_compose() {
    local compose_output="${SCRIPT_DIR}/docker/compose/docker-compose.yml"
    local compose_hash_file="${SCRIPT_DIR}/.setup/compose.hash"

    # Return false if compose file doesn't exist
    [[ ! -f "$compose_output" ]] && return 1

    # Calculate current hash of THIRD_PARTY_IMAGE_SPECS
    local current_hash
    current_hash=$(for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do echo "$spec"; done | md5sum | cut -d' ' -f1)

    # Check if hash file exists and matches
    if [[ -f "$compose_hash_file" ]]; then
        local stored_hash
        stored_hash=$(cat "$compose_hash_file" 2>/dev/null || echo "")
        [[ "$current_hash" == "$stored_hash" ]] && return 1
    fi

    # Hash doesn't match or file doesn't exist - should regenerate
    return 0
}

update_compose_hash() {
    local compose_hash_file="${SCRIPT_DIR}/.setup/compose.hash"
    local hash_dir
    hash_dir="$(dirname "$compose_hash_file")"

    # Create directory if not exists
    mkdir -p "$hash_dir"

    # Calculate and store hash
    local current_hash
    current_hash=$(for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do echo "$spec"; done | md5sum | cut -d' ' -f1)
    echo "$current_hash" > "$compose_hash_file"
}

# ─────────────────────────────────────────────────────────────
# REGENERATE COMPOSE
# ─────────────────────────────────────────────────────────────

cmd_regenerate_compose() {
    section "🔧 Regenerating docker-compose.yml"

    local compose_template="${SCRIPT_DIR}/.setup/templates/docker-compose.yml.template"
    local compose_output="${SCRIPT_DIR}/docker/compose/docker-compose.yml"

    # Create template directory if not exists
    mkdir -p "$(dirname "$compose_template")"

    # Create template from current compose if not exists
    if [[ ! -f "$compose_template" ]]; then
        if [[ -f "$compose_output" ]]; then
            log_detail "Creating template from current docker-compose.yml..."
            cp "$compose_output" "$compose_template"
        else
            log_error "Neither template nor docker-compose.yml found!"
            exit 1
        fi
    fi

    # Copy template to output
    log_detail "Generating ${compose_output}..."
    cp "$compose_template" "$compose_output"

    # Update versions from THIRD_PARTY_IMAGE_SPECS
    log_detail "Updating image versions from THIRD_PARTY_IMAGE_SPECS..."
    local updated=false
    for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do
        local image_ref="${spec%%|*}"
        local image_name="${image_ref%%:*}"
        local image_tag="${image_ref##*:}"

        # Skip if no tag specified
        [[ "$image_name" == "$image_tag" ]] && continue

        # Get current image in docker-compose.yml
        local current_image
        current_image=$(grep "^[[:space:]]*image:[[:space:]]*${image_name}:" "$compose_output" 2>/dev/null | sed 's/^[[:space:]]*image:[[:space:]]*//;s/[[:space:]]*$//' || echo "")

        if [[ -n "$current_image" ]] && [[ "$current_image" != "$image_ref" ]]; then
            # Replace image in docker-compose.yml
            sed -i "s|image:[[:space:]]*${image_name}:[^[:space:]]*|image: ${image_ref}|g" "$compose_output"
            log_detail "   Updated: ${image_name}: ${current_image} → ${image_ref}"
            updated=true
        fi
    done

    if [[ "$updated" == false ]]; then
        log_detail "All versions already up to date ✓"
    else
        log_success "Image versions updated in docker-compose.yml"
    fi

    log_success "✅ docker-compose.yml regenerated successfully"
    echo ""
    echo "Current versions from THIRD_PARTY_IMAGE_SPECS:"
    echo "-------------------------------------------"
    for spec in "${THIRD_PARTY_IMAGE_SPECS[@]}"; do
        local image_ref="${spec%%|*}"
        echo "   • $image_ref"
    done
    echo ""
    echo "To update versions:"
    echo "  1. Edit THIRD_PARTY_IMAGE_SPECS in setup.sh"
    echo "  2. Run: ./setup.sh regenerate-compose"
    echo "  3. Run: ./setup.sh stop && ./setup.sh start"

    # Update hash so we don't regenerate unnecessarily
    update_compose_hash
}

