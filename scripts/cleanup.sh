#!/bin/bash
# Cleanup Script - Remove unused resources

echo "🧹 Cleaning up unused Docker resources..."

# Stop all services
echo "Stopping all services..."
docker compose -f infrastructure/docker/docker-compose.yml down

# Remove dangling images
echo "Removing dangling images..."
docker image prune -f

# Remove unused volumes (WARNING: This deletes data!)
read -p "Remove unused volumes? This will delete all data! (yes/no): " confirm
if [ "$confirm" = "yes" ]; then
    echo "Removing unused volumes..."
    docker volume prune -f
fi

# Remove unused networks
echo "Removing unused networks..."
docker network prune -f

echo "✅ Cleanup completed!"
