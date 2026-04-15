#!/bin/bash
# Comprehensive Test Script for Phase 1.1 & 1.2
# Tests Authentication, Rate Limiting, Network Detection, and Security Features

# Don't exit on error - we want to run all tests
# set -e

BASE_URL="http://localhost:8000"
FAILED_TESTS=0
PASSED_TESTS=0

echo "=========================================="
echo "Minder Phase 1.1 & 1.2 Comprehensive Test"
echo "=========================================="
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test helper functions
test_passed() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED_TESTS++))
}

test_failed() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    echo "  Details: $2"
    ((FAILED_TESTS++))
}

test_warning() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    echo "  Details: $2"
}

# ==========================================
# PHASE 1.1: AUTHENTICATION TESTS
# ==========================================
echo "=== PHASE 1.1: AUTHENTICATION SYSTEM ==="
echo ""

# Test 1.1: Login with correct credentials
echo "Test 1.1: Login with correct credentials"
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')

if echo "$LOGIN_RESPONSE" | grep -q "access_token"; then
    TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token')
    EXPIRES=$(echo "$LOGIN_RESPONSE" | jq -r '.expires_in')
    ROLE=$(echo "$LOGIN_RESPONSE" | jq -r '.user.role')

    if [ "$TOKEN" != "null" ] && [ "$EXPIRES" == "1800" ] && [ "$ROLE" == "admin" ]; then
        test_passed "Login successful with correct credentials"
        echo "  Token: ${TOKEN:0:20}..."
        echo "  Expires in: $EXPIRES seconds"
        echo "  Role: $ROLE"
    else
        test_failed "Login response validation" "Token: $TOKEN, Expires: $EXPIRES, Role: $ROLE"
    fi
else
    test_failed "Login with correct credentials" "No access_token in response"
fi
echo ""

# Test 1.2: Login with incorrect username
echo "Test 1.2: Login with incorrect username"
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"wronguser","password":"admin123"}')

if echo "$LOGIN_RESPONSE" | grep -q "detail"; then
    test_passed "Login failed with incorrect username"
else
    test_failed "Login should fail with incorrect username" "Response: $LOGIN_RESPONSE"
fi
echo ""

# Test 1.3: Login with incorrect password
echo "Test 1.3: Login with incorrect password"
LOGIN_RESPONSE=$(curl -s -X POST "${BASE_URL}/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"wrongpassword"}')

if echo "$LOGIN_RESPONSE" | grep -q "detail"; then
    test_passed "Login failed with incorrect password"
else
    test_failed "Login should fail with incorrect password" "Response: $LOGIN_RESPONSE"
fi
echo ""

# Test 1.4: Access protected endpoint with valid token
echo "Test 1.4: Access protected endpoint with valid token"
if [ -n "$TOKEN" ]; then
    PROTECTED_RESPONSE=$(curl -s "${BASE_URL}/plugins" \
      -H "Authorization: Bearer $TOKEN")

    if echo "$PROTECTED_RESPONSE" | grep -q "plugins"; then
        test_passed "Protected endpoint accessible with valid token"
    else
        test_failed "Protected endpoint should return plugins" "Response: $PROTECTED_RESPONSE"
    fi
else
    test_failed "Cannot test protected endpoint - no token available"
fi
echo ""

# Test 1.5: Access /plugins from trusted network (no auth required)
echo "Test 1.5: Access /plugins from trusted network (no auth required)"
PROTECTED_RESPONSE=$(curl -s -w "\n%{http_code}" "${BASE_URL}/plugins")
HTTP_CODE=$(echo "$PROTECTED_RESPONSE" | tail -n1)

if [ "$HTTP_CODE" == "200" ] && echo "$PROTECTED_RESPONSE" | grep -q "plugins"; then
    test_passed "Trusted network can access /plugins without authentication (by design)"
else
    test_failed "Trusted network should access /plugins without auth" "HTTP Code: $HTTP_CODE"
fi
echo ""

# Test 1.6: Verify /plugins returns proper response structure
echo "Test 1.6: Verify /plugins response structure"
PROTECTED_RESPONSE=$(curl -s "${BASE_URL}/plugins")

if echo "$PROTECTED_RESPONSE" | grep -q '"plugins"' && echo "$PROTECTED_RESPONSE" | grep -q '"total"'; then
    test_passed "/plugins returns proper response structure"
else
    test_failed "/plugins should return plugins list" "Response structure invalid"
fi
echo ""

# ==========================================
# PHASE 1.2: RATE LIMITING TESTS
# ==========================================
echo "=== PHASE 1.2: RATE LIMITING ==="
echo ""

# Test 2.1: Redis connection
echo "Test 2.1: Redis backend connection"
REDIS_PING=$(docker exec redis redis-cli ping 2>/dev/null || echo "ERROR")

if [ "$REDIS_PING" == "PONG" ]; then
    test_passed "Redis backend is connected"
else
    test_failed "Redis backend not connected" "Ping response: $REDIS_PING"
fi
echo ""

# Test 2.2: Standard rate limiting (plugins endpoint) - should allow unlimited on local
echo "Test 2.2: Standard rate limiting test (100 requests)"
RATE_LIMIT_COUNT=0
for i in {1..100}; do
    RESPONSE=$(curl -s "${BASE_URL}/plugins")
    if echo "$RESPONSE" | grep -q "rate_limit_exceeded"; then
        RATE_LIMIT_COUNT=$i
        break
    fi
done

if [ $RATE_LIMIT_COUNT -eq 0 ]; then
    test_passed "Standard rate limiting allows unlimited requests on local network (100/100 passed)"
else
    test_warning "Rate limit triggered at request $RATE_LIMIT_COUNT" "Expected: Unlimited on local network"
fi
echo ""

# Test 2.3: Expensive operations rate limiting (chat endpoint)
echo "Test 2.3: Expensive operations rate limiting test (40 chat requests)"

if [ -n "$TOKEN" ]; then
    CHAT_RATE_LIMIT_COUNT=0
    for i in {1..40}; do
        RESPONSE=$(curl -s -X POST "${BASE_URL}/chat" \
          -H "Content-Type: application/json" \
          -H "Authorization: Bearer $TOKEN" \
          -d '{"message":"test"}')

        if echo "$RESPONSE" | grep -q "rate_limit_exceeded"; then
            CHAT_RATE_LIMIT_COUNT=$i
            break
        fi

        # Small delay to avoid overwhelming
        sleep 0.2
    done

    if [ $CHAT_RATE_LIMIT_COUNT -eq 0 ]; then
        test_passed "Expensive operations allows unlimited on local network (40/40 passed)"
    else
        test_warning "Chat rate limit triggered at request $CHAT_RATE_LIMIT_COUNT" "Expected: Unlimited on local network"
    fi
else
    test_failed "Cannot test chat rate limiting - no token available"
fi
echo ""

# ==========================================
# NETWORK DETECTION TESTS
# ==========================================
echo "=== NETWORK DETECTION ==="
echo ""

# Test 3.1: Network type detection
echo "Test 3.1: Network type detection headers"
NETWORK_HEADERS=$(curl -v "${BASE_URL}/" 2>&1 | grep -i "x-network-type\|x-client-ip")

if echo "$NETWORK_HEADERS" | grep -q "x-network-type"; then
    NETWORK_TYPE=$(echo "$NETWORK_HEADERS" | grep "x-network-type" | awk '{print $3}' | tr -d '\r')
    CLIENT_IP=$(echo "$NETWORK_HEADERS" | grep "x-client-ip" | awk '{print $3}' | tr -d '\r')

    test_passed "Network detection headers present"
    echo "  Network Type: $NETWORK_TYPE"
    echo "  Client IP: $CLIENT_IP"
else
    test_failed "Network detection headers missing"
fi
echo ""

# ==========================================
# SECURITY HEADERS TESTS
# ==========================================
echo "=== SECURITY HEADERS ==="
echo ""

# Test 4.1: Security headers presence
echo "Test 4.1: Security headers check"
SECURITY_HEADERS=$(curl -v "${BASE_URL}/" 2>&1 | grep -i "x-content-type-options\|x-frame-options\|x-xss-protection\|strict-transport-security")

MISSING_HEADERS=0
if ! echo "$SECURITY_HEADERS" | grep -qi "x-content-type-options"; then
    ((MISSING_HEADERS++))
fi
if ! echo "$SECURITY_HEADERS" | grep -qi "x-frame-options"; then
    ((MISSING_HEADERS++))
fi
if ! echo "$SECURITY_HEADERS" | grep -qi "x-xss-protection"; then
    ((MISSING_HEADERS++))
fi
if ! echo "$SECURITY_HEADERS" | grep -qi "strict-transport-security"; then
    ((MISSING_HEADERS++))
fi

if [ $MISSING_HEADERS -eq 0 ]; then
    test_passed "All security headers present"
    echo "  Headers found:"
    echo "$SECURITY_HEADERS" | while read line; do echo "    - $line"; done
else
    test_warning "Some security headers missing" "Missing count: $MISSING_HEADERS"
fi
echo ""

# Test 4.2: Correlation ID presence
echo "Test 4.2: Correlation ID check"
CORRELATION_ID=$(curl -s -D - "${BASE_URL}/health" -o /dev/null | grep -i "x-correlation-id" | awk '{print $2}' | tr -d '\r')

if [ -n "$CORRELATION_ID" ]; then
    test_passed "Correlation ID present"
    echo "  Correlation ID: $CORRELATION_ID"
else
    test_failed "Correlation ID missing"
fi
echo ""

# ==========================================
# HEALTH CHECK TESTS
# ==========================================
echo "=== HEALTH CHECKS ==="
echo ""

# Test 5.1: API Health endpoint
echo "Test 5.1: API health check"
HEALTH_RESPONSE=$(curl -s "${BASE_URL}/health")

if echo "$HEALTH_RESPONSE" | grep -q '"status":"healthy"'; then
    test_passed "API health check returns healthy"
else
    test_failed "API health check failed" "Response: $HEALTH_RESPONSE"
fi
echo ""

# Test 5.2: Container health status
echo "Test 5.2: Container health status"
UNHEALTHY_CONTAINERS=$(docker ps --filter "name=minder" --format "{{.Names}}: {{.Status}}" | grep -v "healthy" | wc -l)

if [ $UNHEALTHY_CONTAINERS -eq 0 ]; then
    test_passed "All Minder containers are healthy"
else
    test_warning "Some containers are not healthy" "Unhealthy count: $UNHEALTHY_CONTAINERS"
fi
echo ""

# ==========================================
# SUMMARY
# ==========================================
echo "=========================================="
echo "TEST SUMMARY"
echo "=========================================="
echo ""
echo "Passed: $PASSED_TESTS"
echo "Failed: $FAILED_TESTS"
echo ""

if [ $FAILED_TESTS -eq 0 ]; then
    echo -e "${GREEN}✓ ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}✗ SOME TESTS FAILED${NC}"
    exit 1
fi
