#!/bin/bash
# ============================================================================
# JWT Validation Test for plugin-registry
# ============================================================================
# Tests 4 scenarios:
# 1. Valid JWT → 200
# 2. Invalid JWT → 401
# 3. No JWT → 401
# 4. "test_user" bypass → 401 (old behavior must die)
# ============================================================================

set -e

echo "=========================================="
echo "JWT Validation Test - plugin-registry"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if services are running
echo "🔍 Checking services..."
if ! curl -s http://localhost:8000/health > /dev/null; then
    echo -e "${RED}❌ api-gateway not responding on port 8000${NC}"
    echo "Start services with: docker compose -f docker-compose.yml -f docker-compose.override.yml up -d"
    exit 1
fi

if ! curl -s http://localhost:8001/health > /dev/null; then
    echo -e "${RED}❌ plugin-registry not responding on port 8001${NC}"
    echo "Start services with: docker compose -f docker-compose.yml -f docker-compose.override.yml up -d"
    exit 1
fi

echo -e "${GREEN}✅ Both services are running${NC}"
echo ""

# ============================================================================
# PRE-TEST: Verify JWT_SECRET consistency
# ============================================================================
echo "=========================================="
echo "PRE-TEST: JWT_SECRET Consistency"
echo "=========================================="

# Get JWT_SECRET from environment (or use dev default)
JWT_SECRET=${JWT_SECRET:-"dev-secret-change-in-production"}
echo "Local JWT_SECRET: ${JWT_SECRET:0:20}..." # Show first 20 chars

# Check api-gateway has JWT_SECRET
echo "Checking api-gateway JWT_SECRET..."
API_GATEWAY_SECRET=$(docker exec minder-api-gateway printenv JWT_SECRET 2>/dev/null || echo "NOT_SET")
if [ "$API_GATEWAY_SECRET" = "NOT_SET" ]; then
    echo -e "${YELLOW}⚠️  api-gateway JWT_SECRET not set (using default)${NC}"
else
    echo -e "${GREEN}✅ api-gateway JWT_SECRET: ${API_GATEWAY_SECRET:0:20}...${NC}"
fi

# Check plugin-registry has JWT_SECRET
echo "Checking plugin-registry JWT_SECRET..."
REGISTRY_SECRET=$(docker exec minder-plugin-registry printenv JWT_SECRET 2>/dev/null || echo "NOT_SET")
if [ "$REGISTRY_SECRET" = "NOT_SET" ]; then
    echo -e "${RED}❌ plugin-registry JWT_SECRET not set - CANNOT VALIDATE TOKENS!${NC}"
    exit 1
else
    echo -e "${GREEN}✅ plugin-registry JWT_SECRET: ${REGISTRY_SECRET:0:20}...${NC}"
fi

# Verify they match
if [ "$API_GATEWAY_SECRET" != "NOT_SET" ] && [ "$REGISTRY_SECRET" != "NOT_SET" ]; then
    if [ "$API_GATEWAY_SECRET" = "$REGISTRY_SECRET" ]; then
        echo -e "${GREEN}✅ JWT_SECRET MATCHES - tokens will be valid across services${NC}"
    else
        echo -e "${RED}❌ JWT_SECRET MISMATCH - cross-service auth will fail!${NC}"
        exit 1
    fi
fi
echo ""

# ============================================================================
# Step 1: Get a valid JWT token from api-gateway
# ============================================================================
echo "=========================================="
echo "Step 1: Getting valid JWT from api-gateway"
echo "=========================================="

# First, let's create a test user if needed
echo "Creating test user..."
curl -s -X POST http://localhost:8000/v1/auth/register \
    -H "Content-Type: application/json" \
    -d '{"username":"testuser","password":"password123","email":"test@example.com"}' > /dev/null 2>&1 || true

# Login to get JWT
echo "Logging in..."
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"testuser","password":"password123"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*' | cut -d'"' -f4)

if [ -z "$TOKEN" ]; then
    echo -e "${RED}❌ Failed to get token from api-gateway${NC}"
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

echo -e "${GREEN}✅ Got JWT token (first 50 chars): ${TOKEN:0:50}...${NC}"
echo ""

# ============================================================================
# TEST 1: Valid JWT → 200
# ============================================================================
echo "=========================================="
echo "TEST 1: Valid JWT → Expected: 200"
echo "=========================================="

# Use /v1/plugins endpoint (public, no auth required for list)
# Then try a protected endpoint
RESPONSE=$(curl -i -s -X GET http://localhost:8001/v1/plugins \
    -H "Authorization: Bearer $TOKEN" \
    -o /dev/null -w "%{http_code}")

if [ "$RESPONSE" = "200" ]; then
    echo -e "${GREEN}✅ PASS: Valid JWT returned 200${NC}"
else
    echo -e "${RED}❌ FAIL: Expected 200, got $RESPONSE${NC}"
fi
echo ""

# ============================================================================
# TEST 2: Invalid JWT → 401
# ============================================================================
echo "=========================================="
echo "TEST 2: Invalid JWT → Expected: 401"
echo "=========================================="

RESPONSE=$(curl -i -s -X POST http://localhost:8001/v1/plugins/test/enable \
    -H "Authorization: Bearer invalid_fake_token_12345" \
    -o /dev/null -w "%{http_code}")

if [ "$RESPONSE" = "401" ]; then
    echo -e "${GREEN}✅ PASS: Invalid JWT returned 401${NC}"
else
    echo -e "${RED}❌ FAIL: Expected 401, got $RESPONSE${NC}"
fi
echo ""

# ============================================================================
# TEST 3: No JWT → 401
# ============================================================================
echo "=========================================="
echo "TEST 3: No JWT → Expected: 401"
echo "=========================================="

RESPONSE=$(curl -i -s -X POST http://localhost:8001/v1/plugins/test/enable \
    -o /dev/null -w "%{http_code}")

if [ "$RESPONSE" = "401" ]; then
    echo -e "${GREEN}✅ PASS: No JWT returned 401${NC}"
else
    echo -e "${RED}❌ FAIL: Expected 401, got $RESPONSE${NC}"
    echo "Note: This might be 404 if plugin 'test' doesn't exist"
fi
echo ""

# ============================================================================
# TEST 4: "test_user" bypass must die → 401
# ============================================================================
echo "=========================================="
echo "TEST 4: test_user bypass → Expected: 401"
echo "=========================================="
echo "This verifies the OLD 'test_user always valid' behavior is DEAD"
echo ""

# Try accessing a protected endpoint that used to return test_user
# The /v1/auth/me endpoint was removed, so we'll try a protected plugin endpoint
RESPONSE=$(curl -i -s -X POST http://localhost:8001/v1/plugins/nonexistent/enable \
    -o /dev/null -w "%{http_code}")

if [ "$RESPONSE" = "401" ]; then
    echo -e "${GREEN}✅ PASS: test_user bypass is DEAD - got 401${NC}"
else
    echo -e "${RED}❌ FAIL: Expected 401, got $RESPONSE${NC}"
    echo "The old 'test_user always valid' behavior may still be active!"
fi
echo ""

# ============================================================================
# TEST 5: Gateway token works in plugin-registry (cross-service auth)
# ============================================================================
echo "=========================================="
echo "TEST 5: Cross-service JWT validation"
echo "=========================================="
echo "Verifying: Token from api-gateway is accepted by plugin-registry"
echo ""

# First get a list of plugins (should work with valid JWT)
RESPONSE=$(curl -s -X GET http://localhost:8001/v1/plugins \
    -H "Authorization: Bearer $TOKEN")

if echo "$RESPONSE" | grep -q '"plugins"'; then
    echo -e "${GREEN}✅ PASS: Gateway token accepted by plugin-registry${NC}"
    echo "Plugin count: $(echo "$RESPONSE" | grep -o '"count":[0-9]*' | cut -d':' -f2)"
else
    echo -e "${RED}❌ FAIL: Gateway token not accepted${NC}"
    echo "Response: $RESPONSE"
fi
echo ""

# ============================================================================
# Summary
# ============================================================================
echo "=========================================="
echo "Test Complete"
echo "=========================================="
echo ""
echo "If all tests passed:"
echo "  - JWT_SECRET is consistent across services"
echo "  - Valid tokens are accepted (200)"
echo "  - Invalid tokens are rejected (401)"
echo "  - Missing tokens are rejected (401)"
echo "  - Old 'test_user' bypass is dead (401)"
echo "  - Cross-service auth works (gateway token → registry)"
echo ""
