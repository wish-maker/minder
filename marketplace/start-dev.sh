#!/bin/bash

# Minder Plugin Marketplace - Quick Start Script
# This script sets up and starts the development environment

set -e

echo "🚀 Minder Plugin Marketplace - Development Environment Setup"
echo "=========================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Check if .env.local exists
if [ ! -f /root/minder/marketplace/.env.local ]; then
    print_warning "Environment file not found. Creating .env.local..."

    cat > /root/minder/marketplace/.env.local << EOF
# API Configuration
NEXT_PUBLIC_API_URL=http://localhost:8000

# Clerk Authentication
# Get your keys from: https://dashboard.clerk.com/
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_test_placeholder
CLERK_SECRET_KEY=sk_test_placeholder

# App Configuration
NEXT_PUBLIC_APP_URL=http://localhost:3000
EOF

    print_warning "Please update .env.local with your Clerk credentials"
    print_warning "Get keys from: https://dashboard.clerk.com/"
    echo ""
fi

# Check if node_modules exists
if [ ! -d /root/minder/marketplace/node_modules ]; then
    echo "📦 Installing dependencies..."
    cd /root/minder/marketplace
    npm install
    print_success "Dependencies installed"
else
    print_success "Dependencies already installed"
fi

echo ""
echo "🔧 Checking backend services..."

# Check if Docker is running
if ! docker ps > /dev/null 2>&1; then
    print_error "Docker is not running. Please start Docker first."
    exit 1
fi

print_success "Docker is running"

# Check if backend services are running
BACKEND_SERVICES=$(docker ps --format "{{.Names}}" | grep -E "(api-gateway|marketplace-service|plugin-registry)" | wc -l)

if [ "$BACKEND_SERVICES" -lt 3 ]; then
    echo ""
    print_warning "Backend services not fully running. Starting backend services..."

    cd /root/minder/infrastructure/docker
    docker-compose up -d

    echo ""
    echo "⏳ Waiting for services to start..."
    sleep 10

    # Verify services are up
    if curl -s http://localhost:8000/health > /dev/null; then
        print_success "Backend services are running"
    else
        print_error "Backend services failed to start. Check logs with: docker-compose logs"
        exit 1
    fi
else
    print_success "Backend services are running"
fi

echo ""
echo "🌐 Starting development server..."
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
print_success "Development server starting at: http://localhost:3000"
echo ""
echo "Available pages:"
echo "  • Home:              http://localhost:3000"
echo "  • Plugin Marketplace: http://localhost:3000/marketplace/plugins"
echo "  • AI Tools:          http://localhost:3000/marketplace/ai-tools"
echo "  • Dashboard:         http://localhost:3000/dashboard"
echo "  • Admin:             http://localhost:3000/admin"
echo "  • Developer Portal:  http://localhost:3000/developer"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
print_warning "Press Ctrl+C to stop the server"
echo ""

# Start the development server
cd /root/minder/marketplace
npm run dev
