#!/bin/bash
# scripts/deploy.sh
set -e

echo "🚀 Deploying Minder..."

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  Warning: .env file not found"
fi

# Build images
echo "📦 Building Docker images..."
docker compose build

# Stop existing containers
echo "⏹️  Stopping existing containers..."
docker compose down

# Start new containers
echo "▶️  Starting new containers..."
docker compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Health check
echo "🏥 Running health checks..."
./scripts/health-check.sh

echo "✅ Deployment complete!"
echo "🌐 API available at: http://localhost:8000"
echo "📊 Grafana available at: http://localhost:3002"
echo "📚 API docs at: http://localhost:8000/docs"
