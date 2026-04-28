#!/bin/bash
# Diagnostics Script - Collect system information

echo "=== Minder Platform Diagnostics ==="
echo ""

echo "Date: $(date)"
echo "Host: $(hostname)"
echo ""

echo "=== Docker Information ==="
docker --version
docker compose version
echo ""

echo "=== Running Services ==="
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

echo "=== Resource Usage ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
echo ""

echo "=== Disk Usage ==="
df -h | grep -E "Filesystem|/dev/"
echo ""

echo "=== Memory Usage ==="
free -h
echo ""

echo "=== Network Connectivity ==="
for port in 8000 8001 8002 8003 8004 8005; do
    if curl -s http://localhost:$port/health > /dev/null; then
        echo "✅ Port $port: Accessible"
    else
        echo "❌ Port $port: Not accessible"
    fi
done
echo ""

echo "=== Recent Logs (Last 20 lines each) ==="
for service in api-gateway plugin-registry marketplace; do
    echo "--- $service ---"
    docker logs minder-$service --tail 20 2>&1 | tail -5
done
echo ""

echo "=== Environment Variables (Sanitized) ==="
docker exec -it minder-postgres env | grep -E "POSTGRES|REDIS" | sed 's/PASSWORD=.*/PASSWORD=***/'
echo ""

echo "=== Database Connections ==="
docker exec -it minder-postgres psql -U minder -c "SELECT count(*) as connections FROM pg_stat_activity;" 2>/dev/null || echo "Cannot check database connections"
echo ""

echo "=== Test Results ==="
pytest tests/unit/ -v --tb=no 2>&1 | tail -5
