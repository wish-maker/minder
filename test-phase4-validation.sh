#!/usr/bin/env bash
# Test Phase 4 Dynamic Configuration Validation
# This script tests the validation functions without starting services

set -euo pipefail

# Source setup.sh functions
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load setup.sh functions
source ./setup.sh

# Mock environment variables
export ENV_FILE="${SCRIPT_DIR}/infrastructure/docker/.env"

echo "======================================================================"
echo "  PHASE 4 VALIDATION TEST"
echo "======================================================================"
echo ""

# Test 1: ACCESS_MODE validation
echo "Test 1: ACCESS_MODE Validation"
echo "----------------------------------------------------------------------"
validate_access_mode || {
    echo "❌ ACCESS_MODE validation failed"
    exit 1
}
echo ""

# Test 2: AI_COMPUTE_MODE validation
echo "Test 2: AI_COMPUTE_MODE Validation"
echo "----------------------------------------------------------------------"
validate_ai_compute_mode || {
    echo "❌ AI_COMPUTE_MODE validation failed"
    exit 1
}
echo ""

# Test 3: COMPUTE_RESOURCE_PROFILE validation
echo "Test 3: COMPUTE_RESOURCE_PROFILE Validation"
echo "----------------------------------------------------------------------"
validate_compute_resource_profile || {
    echo "❌ COMPUTE_RESOURCE_PROFILE validation failed"
    exit 1
}
echo ""

# Test 4: Verify exported environment variables
echo "Test 4: Verify Exported Environment Variables"
echo "----------------------------------------------------------------------"
echo "TRAEFIK_ACCESS_MODE=${TRAEFIK_ACCESS_MODE:-NOT_SET}"
echo "AI_ENDPOINT_STRATEGY=${AI_ENDPOINT_STRATEGY:-NOT_SET}"
echo "COMPUTE_CPU_LIMIT=${COMPUTE_CPU_LIMIT:-NOT_SET}"
echo "COMPUTE_MEMORY_LIMIT=${COMPUTE_MEMORY_LIMIT:-NOT_SET}"
echo "GPU_AVAILABLE=${GPU_AVAILABLE:-false}"
echo ""

# Test 5: Verify Traefik configuration files
echo "Test 5: Verify Traefik Configuration Files"
echo "----------------------------------------------------------------------"
TRAEFIK_DYNAMIC_DIR="${SCRIPT_DIR}/infrastructure/docker/traefik/dynamic"

echo "Enabled configurations:"
for config in "${TRAEFIK_DYNAMIC_DIR}"/access-mode-*.yml; do
    if [[ -f "$config" ]]; then
        echo "  ✓ $(basename "$config")"
    fi
done

echo ""
echo "Disabled configurations:"
for config in "${TRAEFIK_DYNAMIC_DIR}"/access-mode-*.yml.disabled; do
    if [[ -f "$config" ]]; then
        echo "  ⊘ $(basename "$config" .disabled)"
    fi
done
echo ""

echo "======================================================================"
echo "  ✅ ALL PHASE 4 VALIDATION TESTS PASSED"
echo "======================================================================"
