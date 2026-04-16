#!/bin/bash
# scripts/health-check.sh
set -e

MAX_RETRIES=30
RETRY_INTERVAL=2

check_endpoint() {
    local url=$1
    local name=$2

    for i in $(seq 1 $MAX_RETRIES); do
        if curl -f -s "$url" > /dev/null 2>&1; then
            echo "✅ $name is healthy"
            return 0
        fi
        echo "⏳ Waiting for $name... ($i/$MAX_RETRIES)"
        sleep $RETRY_INTERVAL
    done

    echo "❌ $name health check failed"
    return 1
}

check_tcp_port() {
    local host=$1
    local port=$2
    local name=$3

    for i in $(seq 1 $MAX_RETRIES); do
        if timeout 2 bash -c "cat < /dev/null > /dev/tcp/$host/$port" 2>/dev/null; then
            echo "✅ $name is healthy"
            return 0
        fi
        echo "⏳ Waiting for $name... ($i/$MAX_RETRIES)"
        sleep $RETRY_INTERVAL
    done

    echo "❌ $name health check failed"
    return 1
}

echo "🏥 Running health checks..."

check_endpoint "http://localhost:8000/" "Minder API"
check_endpoint "http://localhost:3002" "Grafana"
check_endpoint "http://localhost:8086/ping" "InfluxDB"
check_endpoint "http://localhost:6333/" "Qdrant"
check_tcp_port "localhost" "6379" "Redis"

echo "✅ All services healthy!"
