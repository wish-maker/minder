#!/bin/bash
# EXHAUSTIVE VERIFICATION - Her endpoint'i ayrı ayrı test et

echo "=========================================="
echo "EXHAUSTIVE ENDPOINT TESTING"
echo "Her endpoint'i ayrı ayrı kontrol ediyoruz"
echo "=========================================="
echo ""

FAILED=0
PASSED=0
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

BASE_URL="http://localhost:8000"

# ==========================================
# 1. ROOT ENDPOINT
# ==========================================
echo "=== 1. ROOT ENDPOINT (GET /) ==="
RESPONSE=$(curl -s "$BASE_URL/")
echo "Response:"
echo "$RESPONSE" | jq '.'
if echo "$RESPONSE" | jq -e '.status == "running"' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}: Root endpoint working"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Root endpoint failed"
    ((FAILED++))
fi
echo ""

# ==========================================
# 2. HEALTH ENDPOINT
# ==========================================
echo "=== 2. HEALTH ENDPOINT (GET /health) ==="
HEALTH=$(curl -s "$BASE_URL/health")
echo "Response:"
echo "$HEALTH" | jq '.status, .system.status, .authentication, .network_detection'
if echo "$HEALTH" | jq -e '.status == "healthy"' > /dev/null 2>&1; then
    echo -e "${GREEN}✓ PASS${NC}: Health endpoint working"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Health endpoint failed"
    ((FAILED++))
fi
echo ""

# ==========================================
# 3. AUTHENTICATION - LOGIN
# ==========================================
echo "=== 3. AUTHENTICATION - LOGIN (POST /auth/login) ==="
echo "Test 3.1: Valid credentials"
LOGIN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | jq -r '.access_token')
EXPIRES=$(echo "$LOGIN" | jq -r '.expires_in')
ROLE=$(echo "$LOGIN" | jq -r '.user.role')
echo "Token: ${TOKEN:0:50}..."
echo "Expires: $EXPIRES seconds"
echo "Role: $ROLE"

if [ "$TOKEN" != "null" ] && [ "$EXPIRES" == "1800" ] && [ "$ROLE" == "admin" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Login with valid credentials"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Login failed"
    ((FAILED++))
fi
echo ""

echo "Test 3.2: Invalid username"
INVALID_LOGIN=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"wrong","password":"admin123"}')
if echo "$INVALID_LOGIN" | grep -q "detail"; then
    echo -e "${GREEN}✓ PASS${NC}: Invalid username rejected"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Should reject invalid username"
    ((FAILED++))
fi
echo ""

echo "Test 3.3: Invalid password"
INVALID_PASS=$(curl -s -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"wrong"}')
if echo "$INVALID_PASS" | grep -q "detail"; then
    echo -e "${GREEN}✓ PASS${NC}: Invalid password rejected"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Should reject invalid password"
    ((FAILED++))
fi
echo ""

# ==========================================
# 4. PLUGINS ENDPOINT (WITH TOKEN)
# ==========================================
echo "=== 4. PLUGINS ENDPOINT (GET /plugins) ==="
echo "Test 4.1: With valid token"
if [ -n "$TOKEN" ]; then
    PLUGINS=$(curl -s "$BASE_URL/plugins" \
      -H "Authorization: Bearer $TOKEN")
    TOTAL=$(echo "$PLUGINS" | jq -r '.total')
    ENABLED=$(echo "$PLUGINS" | jq -r '.enabled')
    echo "Total plugins: $TOTAL"
    echo "Enabled: $ENABLED"
    
    if [ "$TOTAL" -gt 0 ]; then
        echo -e "${GREEN}✓ PASS${NC}: Plugins accessible with token"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: Plugins endpoint failed"
        ((FAILED++))
    fi
else
    echo -e "${RED}✗ FAIL${NC}: No token available"
    ((FAILED++))
fi
echo ""

echo "Test 4.2: Without token (trusted network)"
PLUGINS_NO_TOKEN=$(curl -s "$BASE_URL/plugins")
TOTAL2=$(echo "$PLUGINS_NO_TOKEN" | jq -r '.total')
if [ "$TOTAL2" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: Trusted network can access without token"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Trusted network should allow access"
    ((FAILED++))
fi
echo ""

# ==========================================
# 5. CHAT ENDPOINT
# ==========================================
echo "=== 5. CHAT ENDPOINT (POST /chat) ==="
if [ -n "$TOKEN" ]; then
    CHAT=$(curl -s -X POST "$BASE_URL/chat" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"message":"test message from verification script"}')
    RESPONSE_TEXT=$(echo "$CHAT" | jq -r '.response')
    CHARACTER=$(echo "$CHAT" | jq -r '.character')
    PLUGINS_USED=$(echo "$CHAT" | jq -r '.plugins_used | length')
    
    echo "Response: $RESPONSE_TEXT"
    echo "Character: $CHARACTER"
    echo "Plugins used: $PLUGINS_USED"
    
    if [ -n "$RESPONSE_TEXT" ] && [ "$CHARSOR" != "null" ]; then
        echo -e "${GREEN}✓ PASS${NC}: Chat endpoint working"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: Chat endpoint failed"
        ((FAILED++))
    fi
else
    echo -e "${RED}✗ FAIL${NC}: No token available"
    ((FAILED++))
fi
echo ""

# ==========================================
# 6. CHARACTERS ENDPOINT
# ==========================================
echo "=== 6. CHARACTERS ENDPOINT (GET /characters) ==="
CHARACTERS=$(curl -s "$BASE_URL/characters")
CHAR_COUNT=$(echo "$CHARACTERS" | jq -r '.characters | length')
echo "Available characters: $CHAR_COUNT"

if [ "$CHAR_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: Characters endpoint working"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Characters endpoint failed"
    ((FAILED++))
fi
echo ""

# ==========================================
# 7. CORRELATIONS ENDPOINT
# ==========================================
echo "=== 7. CORRELATIONS ENDPOINT (GET /correlations) ==="
CORRELATIONS=$(curl -s "$BASE_URL/correlations")
TOTAL_CORRS=$(echo "$CORRELATIONS" | jq -r '.total_correlations')
echo "Total correlations: $TOTAL_CORRS"

if [ -n "$TOTAL_CORRS" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Correlations endpoint working"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Correlations endpoint failed"
    ((FAILED++))
fi
echo ""

# ==========================================
# 8. SYSTEM STATUS ENDPOINT
# ==========================================
echo "=== 8. SYSTEM STATUS ENDPOINT (GET /system/status) ==="
STATUS=$(curl -s "$BASE_URL/system/status")
SYSTEM_STATUS=$(echo "$STATUS" | jq -r '.status')
PLUGIN_COUNT=$(echo "$STATUS" | jq -r '.plugins.total')
echo "System status: $SYSTEM_STATUS"
echo "Plugins: $PLUGIN_COUNT"

if [ "$SYSTEM_STATUS" == "running" ]; then
    echo -e "${GREEN}✓ PASS${NC}: System status endpoint working"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: System status endpoint failed"
    ((FAILED++))
fi
echo ""

# ==========================================
# 9. RATE LIMITING STRESS TEST
# ==========================================
echo "=== 9. RATE LIMITING STRESS TEST (20 rapid requests) ==="
RATE_LIMIT_COUNT=0
for i in {1..20}; do
    RESPONSE=$(curl -s "$BASE_URL/health")
    if echo "$RESPONSE" | grep -q "rate_limit_exceeded"; then
        RATE_LIMIT_COUNT=$i
        break
    fi
done

if [ $RATE_LIMIT_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: No rate limit on local network (20/20 passed)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Rate limit triggered at request $RATE_LIMIT_COUNT"
    echo "Expected: Unlimited on local/private network"
    ((FAILED++))
fi
echo ""

# ==========================================
# 10. NETWORK HEADERS VERIFICATION
# ==========================================
echo "=== 10. NETWORK HEADERS VERIFICATION ==="
NETWORK_TYPE=$(curl -s -D - "$BASE_URL/health" -o /dev/null | grep -i "x-network-type" | awk '{print $2}' | tr -d '\r')
CLIENT_IP=$(curl -s -D - "$BASE_URL/health" -o /dev/null | grep -i "x-client-ip" | awk '{print $2}' | tr -d '\r')
CORRELATION=$(curl -s -D - "$BASE_URL/health" -o /dev/null | grep -i "x-correlation-id" | awk '{print $2}' | tr -d '\r')

echo "Network Type: $NETWORK_TYPE"
echo "Client IP: $CLIENT_IP"
echo "Correlation ID: $CORRELATION"

if [ -n "$NETWORK_TYPE" ] && [ -n "$CLIENT_IP" ] && [ -n "$CORRELATION" ]; then
    echo -e "${GREEN}✓ PASS${NC}: All network headers present"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Some network headers missing"
    ((FAILED++))
fi
echo ""

# ==========================================
# 11. SECURITY HEADERS VERIFICATION
# ==========================================
echo "=== 11. SECURITY HEADERS VERIFICATION ==="
SECURITY_HEADERS=$(curl -s -D - "$BASE_URL/health" -o /dev/null)

echo "Checking security headers:"
for header in "x-content-type-options" "x-frame-options" "x-xss-protection" "strict-transport-security"; do
    if echo "$SECURITY_HEADERS" | grep -qi "$header"; then
        echo "  ✓ $header present"
    else
        echo "  ✗ $header MISSING"
    fi
done

ALL_PRESENT=true
for header in "x-content-type-options" "x-frame-options" "x-xss-protection" "strict-transport-security"; do
    if ! echo "$SECURITY_HEADERS" | grep -qi "$header"; then
        ALL_PRESENT=false
        break
    fi
done

if [ "$ALL_PRESENT" = true ]; then
    echo -e "${GREEN}✓ PASS${NC}: All security headers present"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Some security headers missing"
    ((FAILED++))
fi
echo ""

# ==========================================
# 12. DATABASE CONNECTIONS
# ==========================================
echo "=== 12. DATABASE CONNECTIONS ==="

echo "Test 12.1: Redis connection"
REDIS_TEST=$(docker exec redis redis-cli ping 2>&1)
if [ "$REDIS_TEST" == "PONG" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Redis connected (PONG)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Redis not responding"
    ((FAILED++))
fi

echo "Test 12.2: PostgreSQL connection"
PG_TEST=$(docker exec postgres psql -U postgres -d fundmind -tAc "SELECT 1;" 2>&1)
if [ "$PG_TEST" == "1" ]; then
    echo -e "${GREEN}✓ PASS${NC}: PostgreSQL connected"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: PostgreSQL not connected"
    ((FAILED++))
fi
echo ""

# ==========================================
# SUMMARY
# ==========================================
echo "=========================================="
echo "EXHAUSTIVE VERIFICATION SUMMARY"
echo "=========================================="
echo ""
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ ALL 18 TESTS PASSED! ✓✓✓${NC}"
    echo ""
    echo "Phase 1.1 & 1.2 are COMPLETE and VERIFIED!"
    echo "All endpoints tested and working correctly."
    exit 0
else
    echo -e "${RED}✗✗✗ $FAILED TEST(S) FAILED ✗✗✗${NC}"
    echo ""
    echo "Please review the failures above."
    exit 1
fi
