#!/bin/bash

# Minder Deployment Script
# Deploys Minder platform using Docker Compose

set -e

echo "🚀 Deploying Minder Platform..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

# Create necessary directories
echo "📁 Creating directories..."
mkdir -p logs data

# Copy environment file if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env file from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env file with your configuration!"
fi

# Build and start containers
echo "🐳 Building Docker images..."
docker-compose build

echo "🚀 Starting containers..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 10

# Check health
echo "🔍 Checking service health..."
if curl -f http://localhost:8000/health &> /dev/null; then
    echo "✅ Minder API is healthy!"
else
    echo "⚠️  Minder API is not responding yet. Wait a moment and check logs."
fi

echo ""
echo "✅ Minder deployment complete!"
echo ""
echo "📍 Access points:"
echo "  - Minder API:      http://localhost:8000"
echo "  - OpenWebUI:       http://localhost:3000"
echo "  - Grafana:         http://localhost:3002 (admin/minder123)"
echo "  - API Docs:        http://localhost:8000/docs"
echo ""
echo "📊 To view logs:"
echo "  docker-compose logs -f minder-api"
echo ""
echo "🛑 To stop:"
echo "  docker-compose down"
