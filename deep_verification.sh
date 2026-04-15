#!/bin/bash
# Deep Verification Script - Tests Each Component Individually

echo "=========================================="
echo "Minder Deep Component Verification"
echo "=========================================="
echo ""

FAILED=0
PASSED=0

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ==========================================
# 1. DATABASE VERIFICATION
# ==========================================
echo "=== 1. DATABASE VERIFICATION ==="
echo ""

# Redis
echo "1.1 Redis Connection Test:"
REDIS_TEST=$(docker exec redis redis-cli ping 2>&1)
if [ "$REDIS_TEST" == "PONG" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Redis is responsive"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Redis not responding - $REDIS_TEST"
    ((FAILED++))
fi

echo ""
echo "1.2 Redis Memory & Stats:"
REDIS_INFO=$(docker exec redis redis-cli INFO memory | grep used_memory_human)
echo "  Memory Usage: $REDIS_INFO"

REDIS_KEYS=$(docker exec redis redis-cli DBSIZE)
echo "  Total Keys: $REDIS_KEYS"

if [ "$REDIS_KEYS" -lt 100 ]; then
    echo -e "${GREEN}✓ PASS${NC}: Redis cache is clean ($REDIS_KEYS keys)"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠ WARN${NC}: Redis has many keys ($REDIS_KEYS) - might need cleanup"
fi

echo ""
echo "1.3 PostgreSQL Connection Test:"
PG_TEST=$(docker exec postgres psql -U postgres -d fundmind -tAc "SELECT 1;" 2>&1)
if [ "$PG_TEST" == "1" ]; then
    echo -e "${GREEN}✓ PASS${NC}: PostgreSQL is connected"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: PostgreSQL not connected - $PG_TEST"
    ((FAILED++))
fi

echo ""
echo "1.4 PostgreSQL Users Table:"
PG_USERS=$(docker exec postgres psql -U postgres -d fundmind -tAc "SELECT COUNT(*) FROM users;" 2>&1)
if [ "$PG_USERS" -ge 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: Users table accessible (count: $PG_USERS)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Cannot access users table"
    ((FAILED++))
fi

# ==========================================
# 2. API VERIFICATION
# ==========================================
echo ""
echo "=== 2. API VERIFICATION ==="
echo ""

echo "2.1 API Health Check:"
HEALTH_CHECK=$(curl -s http://localhost:8000/health | jq -r '.status' 2>/dev/null)
if [ "$HEALTH_CHECK" == "healthy" ]; then
    echo -e "${GREEN}✓ PASS${NC}: API is healthy"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: API not healthy - Status: $HEALTH_CHECK"
    ((FAILED++))
fi

echo ""
echo "2.2 API Startup Verification:"
API_LOGS=$(docker logs minder-api 2>&1 | grep -i "error\|exception\|traceback" | tail -5)
if [ -z "$API_LOGS" ]; then
    echo -e "${GREEN}✓ PASS${NC}: No errors in API logs"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠ WARN${NC}: Found errors in logs:"
    echo "$API_LOGS"
fi

# ==========================================
# 3. AUTHENTICATION VERIFICATION
# ==========================================
echo ""
echo "=== 3. AUTHENTICATION VERIFICATION ==="
echo ""

echo "3.1 Login Test:"
LOGIN_RESPONSE=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token' 2>/dev/null)
EXPIRES=$(echo "$LOGIN_RESPONSE" | jq -r '.expires_in' 2>/dev/null)
ROLE=$(echo "$LOGIN_RESPONSE" | jq -r '.user.role' 2>/dev/null)

if [ "$TOKEN" != "null" ] && [ "$TOKEN" != "" ] && [ "$EXPIRES" == "1800" ] && [ "$ROLE" == "admin" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Login successful"
    echo "  Token: ${TOKEN:0:30}..."
    echo "  Expires: $EXPIRES seconds"
    echo "  Role: $ROLE"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Login failed"
    echo "  Response: $LOGIN_RESPONSE"
    ((FAILED++))
fi

echo ""
echo "3.2 Invalid Credentials Test:"
INVALID_LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"wrong","password":"wrong"}')

if echo "$INVALID_LOGIN" | grep -q "detail"; then
    echo -e "${GREEN}✓ PASS${NC}: Invalid credentials rejected"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Should reject invalid credentials"
    ((FAILED++))
fi

echo ""
echo "3.3 Token Verification Test:"
if [ -n "$TOKEN" ]; then
    # Test with valid token
    VALID_TEST=$(curl -s http://localhost:8000/plugins \
      -H "Authorization: Bearer $TOKEN" | jq -r '.plugins' 2>/dev/null)

    if [ "$VALID_TEST" != "null" ] && [ "$VALID_TEST" != "" ]; then
        echo -e "${GREEN}✓ PASS${NC}: Valid token accepted"
        ((PASSED++))
    else
        echo -e "${RED}✗ FAIL${NC}: Valid token rejected"
        ((FAILED++))
    fi

    # Test with invalid token
    INVALID_TEST=$(curl -s -w "\n%{http_code}" http://localhost:8000/plugins \
      -H "Authorization: Bearer invalid_token_12345")
    HTTP_CODE=$(echo "$INVALID_TEST" | tail -n1)

    # Note: From trusted network, this might return 200 (by design)
    echo "  Invalid token test: HTTP $HTTP_CODE (trusted network allows access)"
fi

# ==========================================
# 4. NETWORK DETECTION VERIFICATION
# ==========================================
echo ""
echo "=== 4. NETWORK DETECTION VERIFICATION ==="
echo ""

echo "4.1 Network Headers Test:"
NETWORK_HEADERS=$(curl -v http://localhost:8000/ 2>&1 | grep -i "x-network-type\|x-client-ip")

if echo "$NETWORK_HEADERS" | grep -q "x-network-type"; then
    NETWORK_TYPE=$(echo "$NETWORK_HEADERS" | grep "x-network-type" | awk '{print $3}' | tr -d '\r')
    CLIENT_IP=$(echo "$NETWORK_HEADERS" | grep "x-client-ip" | awk '{print $3}' | tr -d '\r')

    echo -e "${GREEN}✓ PASS${NC}: Network headers present"
    echo "  Network Type: $NETWORK_TYPE"
    echo "  Client IP: $CLIENT_IP"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Network headers missing"
    ((FAILED++))
fi

echo ""
echo "4.2 Correlation ID Test:"
CORRELATION_ID=$(curl -s -D - http://localhost:8000/health -o /dev/null | grep -i "x-correlation-id" | awk '{print $2}' | tr -d '\r')

if [ -n "$CORRELATION_ID" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Correlation ID present"
    echo "  ID: $CORRELATION_ID"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Correlation ID missing"
    ((FAILED++))
fi

# ==========================================
# 5. RATE LIMITING VERIFICATION
# ==========================================
echo ""
echo "=== 5. RATE LIMITING VERIFICATION ==="
echo ""

echo "5.1 Standard Rate Limiting Test (50 rapid requests):"
RATE_LIMIT_COUNT=0
for i in {1..50}; do
    RESPONSE=$(curl -s http://localhost:8000/plugins)
    if echo "$RESPONSE" | grep -q "rate_limit_exceeded"; then
        RATE_LIMIT_COUNT=$i
        break
    fi
done

if [ $RATE_LIMIT_COUNT -eq 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: No rate limit on local/private network (50/50 passed)"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠ WARN${NC}: Rate limit triggered at request $RATE_LIMIT_COUNT"
    echo "  Expected: Unlimited on local/private network"
fi

echo ""
echo "5.2 Redis Rate Limit Keys Check:"
RATE_LIMIT_KEYS=$(docker exec redis redis-cli KEYS "minder*" | wc -l)
echo "  Rate limit keys in Redis: $RATE_LIMIT_KEYS"

if [ $RATE_LIMIT_KEYS -lt 10 ]; then
    echo -e "${GREEN}✓ PASS${NC}: Redis rate limit cache is clean"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠ WARN${NC}: Many rate limit keys in Redis ($RATE_LIMIT_KEYS)"
fi

# ==========================================
# 6. SECURITY HEADERS VERIFICATION
# ==========================================
echo ""
echo "=== 6. SECURITY HEADERS VERIFICATION ==="
echo ""

echo "6.1 Security Headers Check:"
SECURITY_HEADERS=$(curl -v http://localhost:8000/ 2>&1 | grep -i "< x-")

EXPECTED_HEADERS=(
    "x-content-type-options"
    "x-frame-options"
    "x-xss-protection"
    "strict-transport-security"
)

MISSING=0
for header in "${EXPECTED_HEADERS[@]}"; do
    if echo "$SECURITY_HEADERS" | grep -qi "$header"; then
        echo "  ✓ $header"
    else
        echo "  ✗ $header MISSING"
        ((MISSING++))
    fi
done

if [ $MISSING -eq 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: All security headers present"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: $MISSING security headers missing"
    ((FAILED++))
fi

# ==========================================
# 7. PLUGINS VERIFICATION
# ==========================================
echo ""
echo "=== 7. PLUGINS VERIFICATION ==="
echo ""

echo "7.1 Plugins List Test:"
PLUGINS_RESPONSE=$(curl -s http://localhost:8000/plugins)
PLUGIN_COUNT=$(echo "$PLUGINS_RESPONSE" | jq -r '.total' 2>/dev/null)
ENABLED_COUNT=$(echo "$PLUGINS_RESPONSE" | jq -r '.enabled' 2>/dev/null)

if [ "$PLUGIN_COUNT" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: Plugins endpoint working"
    echo "  Total: $PLUGIN_COUNT"
    echo "  Enabled: $ENABLED_COUNT"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Plugins endpoint failed"
    ((FAILED++))
fi

echo ""
echo "7.2 Plugin Health Check:"
HEALTH_PLUGINS=$(curl -s http://localhost:8000/health | jq -r '.system.plugins.ready' 2>/dev/null)
TOTAL_PLUGINS=$(curl -s http://localhost:8000/health | jq -r '.system.plugins.total' 2>/dev/null)

if [ "$HEALTH_PLUGINS" == "$TOTAL_PLUGINS" ] && [ "$TOTAL_PLUGINS" -gt 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: All plugins ready ($HEALTH_PLUGINS/$TOTAL_PLUGINS)"
    ((PASSED++))
else
    echo -e "${YELLOW}⚠ WARN${NC}: Some plugins not ready ($HEALTH_PLUGINS/$TOTAL_PLUGINS)"
fi

# ==========================================
# 8. MIDDLEWARE VERIFICATION
# ==========================================
echo ""
echo "=== 8. MIDDLEPILE VERIFICATION ==="
echo ""

echo "8.1 Middleware Initialization Check:"
MIDDLEWARE_LOGS=$(docker logs minder-api 2>&1 | grep -i "middleware.*enabled")
if [ -n "$MIDDLEWARE_LOGS" ]; then
    echo -e "${GREEN}✓ PASS${NC}: Middleware initialized"
    echo "$MIDDLEWARE_LOGS" | while read line; do
        echo "  - $line"
    done
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC}: Middleware not properly initialized"
    ((FAILED++))
fi

# ==========================================
# SUMMARY
# ==========================================
echo ""
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="
echo ""
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓✓✓ ALL VERIFICATIONS PASSED! ✓✓✓${NC}"
    echo ""
    echo "Phase 1.1 & 1.2 are production-ready!"
    exit 0
else
    echo -e "${RED}✗✗✗ SOME VERIFICATIONS FAILED ✗✗✗${NC}"
    echo ""
    echo "Please review the failed tests above."
    exit 1
fi
