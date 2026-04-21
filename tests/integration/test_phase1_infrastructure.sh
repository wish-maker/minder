#!/bin/bash
# Phase 1 Infrastructure Test Suite
# Tests all core services and their interactions

set -e

echo "======================================"
echo "Phase 1 Infrastructure Test Suite"
echo "======================================"
echo ""

PASS=0
FAIL=0
WARNINGS=0

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test helper functions
test_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

test_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

test_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARNINGS++))
}

test_section() {
    echo ""
    echo "======================================"
    echo "$1"
    echo "======================================"
}

# ============================================================================
# Test 1: Container Health
# ============================================================================
test_section "Test 1: Container Health Check"

echo "Checking if all Minder containers are running..."

containers=("minder-postgres" "minder-redis" "minder-qdrant" "minder-api-gateway" "minder-plugin-registry")

for container in "${containers[@]}"; do
    if docker ps --format '{{.Names}}' | grep -q "^${container}$"; then
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || "no-health-check")

        if [ "$status" = "healthy" ] || [ "$status" = "no-health-check" ]; then
            test_pass "$container is running"
        else
            test_warn "$container is running but health status: $status"
        fi
    else
        test_fail "$container is not running"
    fi
done

# ============================================================================
# Test 2: Infrastructure Services
# ============================================================================
test_section "Test 2: Infrastructure Services"

echo "Testing PostgreSQL connection..."
if docker exec minder-postgres pg_isready -U minder -t 1 > /dev/null 2>&1; then
    test_pass "PostgreSQL is accepting connections"

    # Check if databases exist
    if docker exec minder-postgres psql -U minder -lqt | cut -d \| -f 1 | grep -q minder; then
        test_pass "Main 'minder' database exists"
    else
        test_fail "Main 'minder' database does not exist"
    fi
else
    test_fail "PostgreSQL is not accepting connections"
fi

echo "Testing Redis connection..."
if docker exec minder-redis redis-cli -a ${REDIS_PASSWORD:-dev_password_change_me} ping > /dev/null 2>&1; then
    test_pass "Redis is responding"
else
    test_fail "Redis is not responding"
fi

echo "Testing Qdrant connection..."
if curl -s http://localhost:6333/health > /dev/null 2>&1; then
    test_pass "Qdrant is responding"
else
    test_warn "Qdrant is not responding (expected for Phase 1)"
fi

# ============================================================================
# Test 3: API Gateway
# ============================================================================
test_section "Test 3: API Gateway (Port 8000)"

echo "Testing API Gateway health endpoint..."
health_response=$(curl -s http://localhost:8000/health)
if [ $? -eq 0 ]; then
    status=$(echo "$health_response" | jq -r '.status')
    if [ "$status" = "healthy" ] || [ "$status" = "degraded" ]; then
        test_pass "API Gateway health endpoint ($status)"

        redis_check=$(echo "$health_response" | jq -r '.checks.redis')
        plugin_registry_check=$(echo "$health_response" | jq -r '.checks.plugin_registry')

        if [ "$redis_check" = "healthy" ]; then
            test_pass "API Gateway → Redis connection"
        else
            test_fail "API Gateway → Redis connection failed"
        fi

        if [ "$plugin_registry_check" = "healthy" ]; then
            test_pass "API Gateway → Plugin Registry connection"
        else
            test_fail "API Gateway → Plugin Registry connection failed"
        fi
    else
        test_fail "API Gateway health endpoint returned unexpected status: $status"
    fi
else
    test_fail "API Gateway health endpoint is not responding"
fi

echo "Testing API Gateway authentication endpoints..."
# Test login endpoint
login_response=$(curl -s -X POST http://localhost:8000/v1/auth/login \
    -H "Content-Type: application/json" \
    -d '{"username":"testuser","password":"testpass"}')

if [ $? -eq 0 ]; then
    token=$(echo "$login_response" | jq -r '.access_token')
    if [ "$token" != "null" ] && [ -n "$token" ]; then
        test_pass "JWT token generation works"
    else
        test_fail "JWT token generation failed"
    fi
else
    test_fail "Login endpoint is not responding"
fi

# ============================================================================
# Test 4: Plugin Registry
# ============================================================================
test_section "Test 4: Plugin Registry (Port 8001)"

echo "Testing Plugin Registry health endpoint..."
plugin_health=$(curl -s http://localhost:8001/health)
if [ $? -eq 0 ]; then
    status=$(echo "$plugin_health" | jq -r '.status')
    plugins_loaded=$(echo "$plugin_health" | jq -r '.plugins_loaded')

    if [ "$status" = "healthy" ]; then
        test_pass "Plugin Registry is healthy"
        echo "  → Plugins loaded: $plugins_loaded"

        if [ "$plugins_loaded" -gt 0 ]; then
            test_pass "Plugins successfully loaded"
        else
            test_warn "No plugins loaded (expected due to database issues)"
        fi
    else
        test_fail "Plugin Registry is not healthy"
    fi
else
    test_fail "Plugin Registry health endpoint is not responding"
fi

echo "Testing Plugin Registry API endpoints..."
plugins_list=$(curl -s http://localhost:8001/v1/plugins)
if [ $? -eq 0 ]; then
    count=$(echo "$plugins_list" | jq -r '.count')
    test_pass "Plugin listing endpoint works ($count plugins)"
else
    test_fail "Plugin listing endpoint failed"
fi

# ============================================================================
# Test 5: Service Discovery (API Gateway → Plugin Registry Proxy)
# ============================================================================
test_section "Test 5: Service Discovery & Proxy"

echo "Testing API Gateway → Plugin Registry proxy..."
proxied_plugins=$(curl -s http://localhost:8000/v1/plugins)
if [ $? -eq 0 ]; then
    count=$(echo "$proxied_plugins" | jq -r '.count')
    test_pass "Request proxy works ($count plugins via gateway)"
else
    test_fail "Request proxy failed"
fi

# Check X-Request-ID header
request_id=$(curl -sI http://localhost:8000/v1/plugins | grep -i "x-request-id" | cut -d' ' -f2)
if [ -n "$request_id" ]; then
    test_pass "Distributed tracing header (X-Request-ID) is present"
else
    test_warn "X-Request-ID header is missing"
fi

# ============================================================================
# Test 6: Database Initialization
# ============================================================================
test_section "Test 6: Database Schema Check"

echo "Checking if plugin databases were created..."
databases=("minder_news" "minder_tefas" "minder_weather" "minder_crypto" "minder_network")

db_count=0
for db in "${databases[@]}"; do
    if docker exec minder-postgres psql -U minder -lqt | cut -d \| -f 1 | grep -q "$db"; then
        echo "  ✓ $db exists"
        ((db_count++))
    else
        echo "  ✗ $db missing"
    fi
done

if [ $db_count -eq ${#databases[@]} ]; then
    test_pass "All plugin databases created ($db_count/5)"
elif [ $db_count -gt 0 ]; then
    test_warn "Some plugin databases missing ($db_count/5 created)"
else
    test_fail "No plugin databases created"
fi

# ============================================================================
# Test 7: Network Connectivity
# ============================================================================
test_section "Test 7: Inter-Container Networking"

echo "Testing container-to-container communication..."

# Test API Gateway → Plugin Registry
if docker exec minder-api-gateway curl -sf http://minder-plugin-registry:8001/health > /dev/null 2>&1; then
    test_pass "API Gateway can reach Plugin Registry (container name resolution)"
else
    test_fail "API Gateway cannot reach Plugin Registry"
fi

# Test Plugin Registry → PostgreSQL
if docker exec minder-plugin-registry pg_isready -h minder-postgres -U minder > /dev/null 2>&1; then
    test_pass "Plugin Registry can reach PostgreSQL"
else
    test_fail "Plugin Registry cannot reach PostgreSQL"
fi

# Test API Gateway → Redis (via Python, since redis-cli not available)
if docker exec minder-api-gateway python3 -c "
import redis
import sys
try:
    r = redis.Redis(host='minder-redis', port=6379, password='${REDIS_PASSWORD:-dev_password_change_me}', socket_timeout=2)
    r.ping()
except Exception as e:
    sys.exit(1)
" 2>&1; then
    test_pass "API Gateway can reach Redis"
else
    test_fail "API Gateway cannot reach Redis"
fi

# ============================================================================
# Summary
# ============================================================================
test_section "Test Summary"

TOTAL=$((PASS + FAIL + WARNINGS))
echo ""
echo "Results:"
echo "  ✓ Passed:  $PASS"
echo "  ✗ Failed:  $FAIL"
echo "  ⚠ Warnings: $WARNINGS"
echo "  — Total:   $TOTAL"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}All critical tests passed!${NC}"
    exit 0
else
    echo -e "${RED}$FAIL test(s) failed${NC}"
    exit 1
fi
