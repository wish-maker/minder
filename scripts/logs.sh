#!/bin/bash
# View logs script

if [ -z "$1" ]; then
    echo "Usage: ./logs.sh [service-name]"
    echo ""
    echo "Available services:"
    echo "  all        - All services"
    echo "  api-gateway"
    echo "  plugin-registry"
    echo "  marketplace"
    echo "  plugin-state-manager"
    echo "  ai-services"
    echo "  model-management"
    echo "  postgres"
    echo "  redis"
    echo "  qdrant"
    echo "  ollama"
    echo "  neo4j"
    exit 1
fi

if [ "$1" = "all" ]; then
    docker compose -f infrastructure/docker/docker-compose.yml logs -f --tail=100
else
    docker compose -f infrastructure/docker/docker-compose.yml logs -f --tail=100 "$1"
fi
