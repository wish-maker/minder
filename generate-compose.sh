#!/bin/bash
# ============================================================================
# Minder Platform - Docker Compose Generator
# ============================================================================
# Generates docker-compose.yml from template using setup.sh version specs
# ============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_TEMPLATE="${SCRIPT_DIR}/.setup/templates/docker-compose.yml.template"
COMPOSE_OUTPUT="${SCRIPT_DIR}/infrastructure/docker/docker-compose.yml"
SETUP_SH="${SCRIPT_DIR}/setup.sh"

echo "🔧 Generating docker-compose.yml from setup.sh version specs..."

# Extract THIRD_PARTY_IMAGE_SPECS from setup.sh
declare -A IMAGE_MAP
while IFS='|' read -r image_ref stable_tag constraint; do
    # Extract just the image name and tag
    if [[ "$image_ref" =~ ^([^:]+):(.+)$ ]]; then
        image_name="${BASH_REMATCH[1]}"
        image_tag="${BASH_REMATCH[2]}"
        IMAGE_MAP["$image_name"]="$image_ref"
    fi
done < <(grep -A 20 "THIRD_PARTY_IMAGE_SPECS=" "$SETUP_SH" | grep '^[[:space:]]*"' | sed 's/^[[:space:]]*"\(.*\)"$/\1/')

# Check if template exists
if [[ ! -f "$COMPOSE_TEMPLATE" ]]; then
    echo "❌ Template not found: $COMPOSE_TEMPLATE"
    echo "   Creating from current docker-compose.yml..."
    mkdir -p "$(dirname "$COMPOSE_TEMPLATE")"
    cp "$COMPOSE_OUTPUT" "$COMPOSE_TEMPLATE"
fi

# Copy template to output
cp "$COMPOSE_TEMPLATE" "$COMPOSE_OUTPUT"

echo "✅ docker-compose.yml generated successfully"
echo "   Version specs from: $SETUP_SH"
echo ""
echo "Current versions:"
for image_ref in "${IMAGE_MAP[@]}"; do
    echo "   - $image_ref"
done

echo ""
echo "To update versions:"
echo "  1. Edit $SETUP_SH"
echo "  2. Update THIRD_PARTY_IMAGE_SPECS array"
echo "  3. Run: ./setup.sh regenerate-compose"
