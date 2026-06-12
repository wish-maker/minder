#!/bin/bash
# Schema Registry Verification Script

set -e

echo "🔍 Verifying Schema Registry Setup..."
echo ""

# Check if Schema Registry is running
echo "1. Checking Schema Registry service..."
if curl -s -f http://localhost:8082/health > /dev/null 2>&1; then
    echo "   ✅ Schema Registry is running"
else
    echo "   ❌ Schema Registry is not accessible"
    echo "   Start it with: docker compose -f infrastructure/docker/docker-compose.yml up -d schema-registry"
    exit 1
fi

# Check health endpoint
echo ""
echo "2. Checking health status..."
HEALTH=$(curl -s http://localhost:8082/health)
if echo "$HEALTH" | grep -q "UP"; then
    echo "   ✅ Schema Registry is healthy"
else
    echo "   ⚠️  Health status: $HEALTH"
fi

# Check available API endpoints
echo ""
echo "3. Checking API availability..."
if curl -s -f http://localhost:8082/apis/registry/v2 > /dev/null 2>&1; then
    echo "   ✅ Registry API v2 is available"
else
    echo "   ❌ Registry API v2 is not available"
fi

# Check UI
echo ""
echo "4. Checking Web UI..."
if curl -s -f http://localhost:8082/ > /dev/null 2>&1; then
    echo "   ✅ Web UI is available at http://localhost:8082"
else
    echo "   ⚠️  Web UI might not be fully loaded"
fi

# Test basic operations
echo ""
echo "5. Testing basic operations..."
echo "   Listing artifact groups..."
GROUPS=$(curl -s http://localhost:8082/apis/registry/v2/groups)
if echo "$GROUPS" | grep -q "groups"; then
    echo "   ✅ Can list artifact groups"
else
    echo "   ⚠️  Unable to list groups (expected for empty registry)"
fi

echo ""
echo "✨ Schema Registry verification complete!"
echo ""
echo "📚 Next steps:"
echo "   - Access the UI: http://localhost:8082"
echo "   - API Documentation: http://localhost:8082/apis/registry/v2/docs"
echo "   - Health: http://localhost:8082/health"
echo "   - Metrics: http://localhost:8082/metrics"
