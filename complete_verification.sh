#!/bin/bash
# COMPLETE VERIFICATION - Her şeyi sıfırdan test et

echo "=========================================="
echo "COMPLETE VERIFICATION - SIFIRDAN TEST"
echo "=========================================="
echo ""

FAILED=0
PASSED=0

# 1. Container Status
echo "=== 1. ALL CONTAINERS STATUS ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep minder
if [ $? -eq 0 ]; then
    echo "✓ Containers running"
    ((PASSED++))
else
    echo "✗ Container issue"
    ((FAILED++))
fi
echo ""

# 2. API Root Endpoint
echo "=== 2. ROOT ENDPOINT ==="
ROOT=$(curl -s http://localhost:8000/)
echo "$ROOT" | jq -r '.status' 2>/dev/null
if echo "$ROOT" | jq -e '.status == "running"' > /dev/null 2>&1; then
    echo "✓ Root endpoint working"
    ((PASSED++))
else
    echo "✗ Root endpoint failed"
    ((FAILED++))
fi
echo ""

# 3. Health Endpoint (no rate limit)
echo "=== 3. HEALTH ENDPOINT ==="
HEALTH=$(curl -s http://localhost:8000/health)
echo "$HEALTH" | jq -r '.status' 2>/dev/null
if echo "$HEALTH" | jq -e '.status == "healthy"' > /dev/null 2>&1; then
    echo "✓ Health endpoint working"
    ((PASSED++))
else
    echo "✗ Health endpoint failed"
    echo "Response: $HEALTH"
    ((FAILED++))
fi
echo ""

# 4. Authentication - Login
echo "=== 4. AUTHENTICATION - LOGIN ==="
LOGIN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')
TOKEN=$(echo "$LOGIN" | jq -r '.access_token' 2>/dev/null)
if [ "$TOKEN" != "null" ] && [ -n "$TOKEN" ]; then
    echo "✓ Login successful"
    echo "  Token: ${TOKEN:0:40}..."
    ((PASSED++))
else
    echo "✗ Login failed"
    echo "  Response: $LOGIN"
    ((FAILED++))
fi
echo ""

# 5. Protected Endpoint with Token
echo "=== 5. PROTECTED ENDPOINT (WITH TOKEN) ==="
if [ -n "$TOKEN" ]; then
    PLUGINS=$(curl -s http://localhost:8000/plugins \
      -H "Authorization: Bearer $TOKEN")
    TOTAL=$(echo "$PLUGINS" | jq -r '.total' 2>/dev/null)
    if [ "$TOTAL" -gt 0 ]; then
        echo "✓ Protected endpoint works with token"
        echo "  Plugins: $TOTAL total"
        ((PASSED++))
    else
        echo "✗ Protected endpoint failed"
        echo "  Response: $PLUGINS"
        ((FAILED++))
    fi
else
    echo "✗ Skip - no token available"
    ((FAILED++))
fi
echo ""

# 6. Network Detection Headers
echo "=== 6. NETWORK DETECTION HEADERS ==="
NETWORK_TYPE=$(curl -s -D - http://localhost:8000/health -o /dev/null | grep -i "x-network-type" | awk '{print $2}' | tr -d '\r')
if [ -n "$NETWORK_TYPE" ]; then
    echo "✓ Network detection working"
    echo "  Type: $NETWORK_TYPE"
    ((PASSED++))
else
    echo "✗ Network detection failed"
    ((FAILED++))
fi
echo ""

# 7. Security Headers
echo "=== 7. SECURITY HEADERS ==="
HEADERS=$(curl -s -D - http://localhost:8000/health -o /dev/null)
MISSING=0
for header in "x-content-type-options" "x-frame-options" "x-xss-protection" "strict-transport-security"; do
    if echo "$HEADERS" | grep -qi "$header"; then
        echo "  ✓ $header"
    else
        echo "  ✗ $header MISSING"
        ((MISSING++))
    fi
done
if [ $MISSING -eq 0 ]; then
    echo "✓ All security headers present"
    ((PASSED++))
else
    echo "✗ $MISSING security headers missing"
    ((FAILED++))
fi
echo ""

# 8. Chat Endpoint
echo "=== 8. CHAT ENDPOINT ==="
if [ -n "$TOKEN" ]; then
    CHAT=$(curl -s -X POST http://localhost:8000/chat \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"message":"test message"}')
    if echo "$CHAT" | jq -e '.response' > /dev/null 2>&1; then
        echo "✓ Chat endpoint working"
        echo "  Character: $(echo "$CHAT" | jq -r '.character')"
        ((PASSED++))
    else
        echo "✗ Chat endpoint failed"
        echo "  Response: $CHAT"
        ((FAILED++))
    fi
else
    echo "✗ Skip - no token available"
    ((FAILED++))
fi
echo ""

# 9. Rate Limiting (local network should be unlimited)
echo "=== 9. RATE LIMITING (10 rapid requests) ==="
RATE_LIMIT_HIT=0
for i in {1..10}; do
    RESPONSE=$(curl -s http://localhost:8000/health)
    if echo "$RESPONSE" | grep -q "rate_limit_exceeded"; then
        RATE_LIMIT_HIT=1
        break
    fi
done
if [ $RATE_LIMIT_HIT -eq 0 ]; then
    echo "✓ No rate limit on local network (10/10 passed)"
    ((PASSED++))
else
    echo "✗ Rate limit triggered on local network"
    ((FAILED++))
fi
echo ""

# 10. Database Connections
echo "=== 10. DATABASE CONNECTIONS ==="

# Redis
REDIS_PING=$(docker exec redis redis-cli ping 2>/dev/null)
if [ "$REDIS_PING" == "PONG" ]; then
    echo "  ✓ Redis: PONG"
    REDIS_OK=1
else
    echo "  ✗ Redis: Failed"
    REDIS_OK=0
fi

# PostgreSQL
PG_TEST=$(docker exec postgres psql -U postgres -d fundmind -tAc "SELECT 1;" 2>/dev/null)
if [ "$PG_TEST" == "1" ]; then
    echo "  ✓ PostgreSQL: Connected"
    PG_OK=1
else
    echo "  ✗ PostgreSQL: Failed"
    PG_OK=0
fi

if [ $REDIS_OK -eq 1 ] && [ $PG_OK -eq 1 ]; then
    echo "✓ All databases connected"
    ((PASSED++))
else
    echo "✗ Database connection issues"
    ((FAILED++))
fi
echo ""

# SUMMARY
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="
echo "Passed: $PASSED"
echo "Failed: $FAILED"
echo ""

if [ $FAILED -eq 0 ]; then
    echo "✅ ALL VERIFICATIONS PASSED!"
    echo "Phase 1.1 & 1.2 are COMPLETE and WORKING"
    exit 0
else
    echo "❌ SOME VERIFICATIONS FAILED"
    echo "Please review the failures above"
    exit 1
fi
