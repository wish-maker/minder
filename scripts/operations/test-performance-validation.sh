#!/usr/bin/env bash
# Simple Phase 4 Test - Direct validation without sourcing setup.sh

set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/infrastructure/docker/.env"

echo "======================================================================"
echo "  PHASE 4 DYNAMIC CONFIGURATION TEST"
echo "======================================================================"
echo ""

# Test 1: Check environment variables exist
echo "Test 1: Verify .env has dynamic configuration variables"
echo "----------------------------------------------------------------------"
if grep -q "^ACCESS_MODE=" "$ENV_FILE" && \
   grep -q "^AI_COMPUTE_MODE=" "$ENV_FILE" && \
   grep -q "^COMPUTE_RESOURCE_PROFILE=" "$ENV_FILE"; then
    echo "✓ All dynamic configuration variables present in .env"
else
    echo "❌ Missing dynamic configuration variables"
    exit 1
fi
echo ""

# Test 2: Read current values
echo "Test 2: Read current configuration values"
echo "----------------------------------------------------------------------"
ACCESS_MODE=$(grep "^ACCESS_MODE=" "$ENV_FILE" | cut -d= -f2)
AI_COMPUTE_MODE=$(grep "^AI_COMPUTE_MODE=" "$ENV_FILE" | cut -d= -f2)
COMPUTE_PROFILE=$(grep "^COMPUTE_RESOURCE_PROFILE=" "$ENV_FILE" | cut -d= -f2)

echo "ACCESS_MODE=$ACCESS_MODE"
echo "AI_COMPUTE_MODE=$AI_COMPUTE_MODE"
echo "COMPUTE_RESOURCE_PROFILE=$COMPUTE_PROFILE"
echo ""

# Test 3: Validate ACCESS_MODE value
echo "Test 3: Validate ACCESS_MODE value"
echo "----------------------------------------------------------------------"
case "$ACCESS_MODE" in
    local|vpn|public)
        echo "✓ ACCESS_MODE is valid: $ACCESS_MODE"
        ;;
    *)
        echo "❌ Invalid ACCESS_MODE: $ACCESS_MODE"
        exit 1
        ;;
esac
echo ""

# Test 4: Validate AI_COMPUTE_MODE value
echo "Test 4: Validate AI_COMPUTE_MODE value"
echo "----------------------------------------------------------------------"
case "$AI_COMPUTE_MODE" in
    internal|external|hybrid)
        echo "✓ AI_COMPUTE_MODE is valid: $AI_COMPUTE_MODE"
        ;;
    *)
        echo "❌ Invalid AI_COMPUTE_MODE: $AI_COMPUTE_MODE"
        exit 1
        ;;
esac
echo ""

# Test 5: Validate COMPUTE_RESOURCE_PROFILE value
echo "Test 5: Validate COMPUTE_RESOURCE_PROFILE value"
echo "----------------------------------------------------------------------"
case "$COMPUTE_PROFILE" in
    low|medium|high|enterprise)
        echo "✓ COMPUTE_RESOURCE_PROFILE is valid: $COMPUTE_PROFILE"
        ;;
    *)
        echo "❌ Invalid COMPUTE_RESOURCE_PROFILE: $COMPUTE_PROFILE"
        exit 1
        ;;
esac
echo ""

# Test 6: Check Traefik configuration files
echo "Test 6: Verify Traefik dynamic configuration files"
echo "----------------------------------------------------------------------"
TRAEFIK_DIR="${SCRIPT_DIR}/infrastructure/docker/traefik/dynamic"
CONFIG_COUNT=0

for mode in local vpn public; do
    if [[ -f "${TRAEFIK_DIR}/access-mode-${mode}.yml" ]]; then
        echo "✓ Found (active): access-mode-${mode}.yml"
        CONFIG_COUNT=$((CONFIG_COUNT + 1))
    elif [[ -f "${TRAEFIK_DIR}/access-mode-${mode}.yml.disabled" ]]; then
        echo "⊘ Found (disabled): access-mode-${mode}.yml"
        CONFIG_COUNT=$((CONFIG_COUNT + 1))
    else
        echo "❌ Missing: access-mode-${mode}.yml (both active and disabled)"
        exit 1
    fi
done

if [[ $CONFIG_COUNT -eq 3 ]]; then
    echo "✓ All 3 Traefik access mode configurations present"
else
    echo "❌ Only $CONFIG_COUNT/3 configurations found"
    exit 1
fi
echo ""

# Test 7: Check which config is currently active
echo "Test 7: Identify currently active Traefik configuration"
echo "----------------------------------------------------------------------"
ACTIVE_CONFIG=""
for mode in local vpn public; do
    if [[ -f "${TRAEFIK_DIR}/access-mode-${mode}.yml" ]] && \
       [[ ! -f "${TRAEFIK_DIR}/access-mode-${mode}.yml.disabled" ]]; then
        ACTIVE_CONFIG="$mode"
        break
    fi
done

if [[ -n "$ACTIVE_CONFIG" ]]; then
    echo "✓ Active configuration: access-mode-${ACTIVE_CONFIG}.yml"
    if [[ "$ACTIVE_CONFIG" == "$ACCESS_MODE" ]]; then
        echo "✓ Active configuration matches ACCESS_MODE setting"
    else
        echo "⚠ Warning: Active config (${ACTIVE_CONFIG}) doesn't match ACCESS_MODE (${ACCESS_MODE})"
    fi
else
    echo "⚠ Warning: No active Traefik configuration found"
fi
echo ""

echo "======================================================================"
echo "  ✅ ALL PHASE 4 TESTS PASSED"
echo "======================================================================"
echo ""
echo "Configuration Summary:"
echo "  Access Mode: $ACCESS_MODE"
echo "  AI Compute Mode: $AI_COMPUTE_MODE"
echo "  Resource Profile: $COMPUTE_PROFILE"
echo "  Active Traefik Config: ${ACTIVE_CONFIG:-none}"
echo ""
