#!/bin/bash
# Health Check Script for Minder Platform

services=(
    "8000:API Gateway"
    "8001:Plugin Registry"
    "8002:Marketplace"
    "8003:Plugin State Manager"
    "8004:AI Services"
    "8005:Model Management"
)

all_healthy=true

for service in "${services[@]}"; do
    port=$(echo $service | cut -d: -f1)
    name=$(echo $service | cut -d: -f2)
    
    if curl -s http://localhost:$port/health > /dev/null 2>&1; then
        echo "✅ $name (port $port): Healthy"
    else
        echo "❌ $name (port $port): Not responding"
        all_healthy=false
    fi
done

if [ "$all_healthy" = true ]; then
    echo ""
    echo "🎉 All services are healthy!"
    exit 0
else
    echo ""
    echo "⚠️  Some services are not healthy. Check logs:"
    echo "docker compose -f infrastructure/docker/docker-compose.yml logs"
    exit 1
fi
