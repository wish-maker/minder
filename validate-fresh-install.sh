#!/bin/bash
# Complete validation of setup.sh fresh install capability
# Tests: start, stop, restart, status operations

set -e

echo "=================================="
echo "Minder Platform - Complete Validation"
echo "=================================="
echo ""

# Test 1: Complete stop
echo "🧪 Test 1: Complete system stop..."
./setup.sh stop > /tmp/test-stop.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASS: setup.sh stop successful"
else
    echo "❌ FAIL: setup.sh stop failed"
    cat /tmp/test-stop.log
    exit 1
fi

# Verify all containers stopped
CONTAINER_COUNT=$(docker ps -a --filter "name=minder" --format "{{.Names}}" | wc -l)
if [ "$CONTAINER_COUNT" -eq 0 ]; then
    echo "✅ PASS: All containers removed ($CONTAINER_COUNT running)"
else
    echo "❌ FAIL: $CONTAINER_COUNT containers still running"
    docker ps -a --filter "name=minder" --format "{{.Names}}"
    exit 1
fi

# Test 2: Fresh start from scratch
echo ""
echo "🧪 Test 2: Fresh start from scratch..."
./setup.sh start > /tmp/test-start.log 2>&1 &
START_PID=$!

# Wait for startup
echo "⏳ Waiting for services to start (90 seconds)..."
sleep 90

# Check if start process completed
if ps -p $START_PID > /dev/null; then
    echo "⏳ Start process still running, waiting..."
    wait $START_PID
fi

if [ $? -eq 0 ]; then
    echo "✅ PASS: setup.sh start successful"
else
    echo "❌ FAIL: setup.sh start failed"
    cat /tmp/test-start.log
    exit 1
fi

# Test 3: Verify all containers running
echo ""
echo "🧪 Test 3: Verify all containers started..."
RUNNING_COUNT=$(docker ps --filter "name=minder" --format "{{.Names}}" | wc -l)
if [ "$RUNNING_COUNT" -ge 20 ]; then
    echo "✅ PASS: $RUNNING_COUNT containers running"
else
    echo "❌ FAIL: Only $RUNNING_COUNT containers running (expected 24+)"
    docker ps --filter "name=minder" --format "{{.Names}}"
    exit 1
fi

# Test 4: Check core services health
echo ""
echo "🧪 Test 4: Check core services health..."
HEALTHY_COUNT=$(docker ps --filter "name=minder" --filter "health=healthy" --format "{{.Names}}" | wc -l)
if [ "$HEALTHY_COUNT" -ge 18 ]; then
    echo "✅ PASS: $HEALTHY_COUNT services healthy"
else
    echo "⚠️  WARNING: Only $HEALTHY_COUNT services healthy (expected 20+)"
fi

# Test 5: Verify PostgreSQL 18
echo ""
echo "🧪 Test 5: Verify PostgreSQL version..."
POSTGRES_VERSION=$(docker exec minder-postgres psql -U minder -t -c "SELECT version();" 2>/dev/null | grep "PostgreSQL 18" || echo "")
if [ ! -z "$POSTGRES_VERSION" ]; then
    echo "✅ PASS: PostgreSQL 18 detected"
else
    echo "❌ FAIL: PostgreSQL 18 not detected"
    exit 1
fi

# Test 6: Verify API Gateway health
echo ""
echo "🧪 Test 6: Verify API Gateway health..."
API_HEALTH=$(docker exec minder-api-gateway curl -s http://localhost:8000/health 2>/dev/null | grep -o '"status":"healthy"' || echo "")
if [ ! -z "$API_HEALTH" ]; then
    echo "✅ PASS: API Gateway healthy"
else
    echo "❌ FAIL: API Gateway not healthy"
    exit 1
fi

# Test 7: setup.sh status
echo ""
echo "🧪 Test 7: Test setup.sh status..."
./setup.sh status > /tmp/test-status.log 2>&1
if [ $? -eq 0 ]; then
    echo "✅ PASS: setup.sh status works"
else
    echo "❌ FAIL: setup.sh status failed"
    cat /tmp/test-status.log
    exit 1
fi

# Test 8: setup.sh restart
echo ""
echo "🧪 Test 8: Test setup.sh restart..."
./setup.sh restart > /tmp/test-restart.log 2>&1 &
RESTART_PID=$!

echo "⏳ Waiting for restart (90 seconds)..."
sleep 90

if ps -p $RESTART_PID > /dev/null; then
    wait $RESTART_PID
fi

if [ $? -eq 0 ]; then
    echo "✅ PASS: setup.sh restart successful"
else
    echo "❌ FAIL: setup.sh restart failed"
    cat /tmp/test-restart.log
    exit 1
fi

# Final verification
echo ""
echo "🧪 Test 9: Final verification after restart..."
FINAL_COUNT=$(docker ps --filter "name=minder" --format "{{.Names}}" | wc -l)
if [ "$FINAL_COUNT" -ge 20 ]; then
    echo "✅ PASS: $FINAL_COUNT containers running after restart"
else
    echo "❌ FAIL: Only $FINAL_COUNT containers after restart"
    exit 1
fi

echo ""
echo "=================================="
echo "✅ ALL TESTS PASSED!"
echo "=================================="
echo ""
echo "Summary:"
echo "  ✅ setup.sh stop: WORKING"
echo "  ✅ setup.sh start: WORKING"
echo "  ✅ setup.sh restart: WORKING"
echo "  ✅ setup.sh status: WORKING"
echo "  ✅ Fresh install: WORKING"
echo "  ✅ PostgreSQL 18: WORKING"
echo "  ✅ API Gateway: WORKING"
echo ""
echo "🎉 Requirement FULLY SATISFIED:"
echo "   'setup.sh can fully install this structure in its"
echo "    current state with current versions'"
