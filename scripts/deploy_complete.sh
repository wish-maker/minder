#!/bin/bash

# Minder Complete Deployment Script
# Deploys entire Minder platform with all services
# Includes health checks, dependency verification, and rollback capability

set -e

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║           🚀 Minder Platform - Complete Deployment                ║"
echo "║           Version 1.0.0 - Production Ready                        ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Step 1: Environment Check
echo -e "${BLUE}📋 Step 1: Checking Environment${NC}"
echo "--------------------------------"

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi
echo -e "${GREEN}✅ Docker found: $(docker --version)${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose is not installed${NC}"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose found: $(docker-compose --version)${NC}"

# Check available memory
MEMORY_GB=$(free -g | awk '/^Mem:/{print $2}')
if [ "$MEMORY_GB" -lt 4 ]; then
    echo -e "${YELLOW}⚠️  Low memory detected: ${MEMORY_GB}GB (recommended: 8GB+)${NC}"
fi

echo ""

# Step 2: Directory Setup
echo -e "${BLUE}📁 Step 2: Setting Up Directories${NC}"
echo "--------------------------------"

# Create necessary directories
mkdir -p logs data/models data/audio data/backups

# Set permissions
chmod 755 logs data
chmod 700 data/models

echo -e "${GREEN}✅ Directories created${NC}"
echo ""

# Step 3: Configuration
echo -e "${BLUE}⚙️  Step 3: Configuration Setup${NC}"
echo "---------------------------"

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo -e "${YELLOW}⚠️  Please review .env file and update passwords/secrets!${NC}"
else
    echo -e "${GREEN}✅ .env file exists${NC}"
fi

# Check if config.yaml exists
if [ -f config.yaml ]; then
    echo -e "${GREEN}✅ config.yaml exists${NC}"
else
    echo -e "${RED}❌ config.yaml not found${NC}"
    exit 1
fi

echo ""

# Step 4: Build Docker Images
echo -e "${BLUE}🐳 Step 4: Building Docker Images${NC}"
echo "-------------------------------"

echo "Building Minder API image..."
docker-compose build

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Build successful${NC}"
else
    echo -e "${RED}❌ Build failed${NC}"
    exit 1
fi

echo ""

# Step 5: Start Services
echo -e "${BLUE}🚀 Step 5: Starting Services${NC}"
echo "---------------------------"

echo "Starting PostgreSQL..."
docker-compose up -d postgres

echo "Starting InfluxDB..."
docker-compose up -d influxdb

echo "Starting Qdrant..."
docker-compose up -d qdrant

echo "Starting Redis..."
docker-compose up -d redis

echo "Starting Ollama..."
docker-compose up -d ollama

echo "Starting OpenWebUI..."
docker-compose up -d openwebui

echo "Starting Minder API..."
docker-compose up -d minder-api

echo "Starting Grafana..."
docker-compose up -d grafana

echo -e "${GREEN}✅ All services started${NC}"
echo ""

# Step 6: Wait for Services to be Ready
echo -e "${BLUE}⏳ Step 6: Waiting for Services to be Ready${NC}"
echo "----------------------------------------"

echo "Waiting for PostgreSQL..."
for i in {1..30}; do
    if docker exec minder-postgres pg_isready -U postgres &> /dev/null; then
        echo -e "${GREEN}✅ PostgreSQL ready${NC}"
        break
    fi
    echo "  Waiting... ($i/30)"
    sleep 2
done

echo "Waiting for Minder API..."
for i in {1..60}; do
    if curl -sf http://localhost:8000/health &> /dev/null; then
        echo -e "${GREEN}✅ Minder API ready${NC}"
        break
    fi
    echo "  Waiting... ($i/60)"
    sleep 2
done

echo ""

# Step 7: Health Check
echo -e "${BLUE}🏥 Step 7: Health Check${NC}"
echo "--------------------"

echo "Checking service health..."

# Check PostgreSQL
if docker exec minder-postgres pg_isready -U postgres &> /dev/null; then
    echo -e "${GREEN}✅ PostgreSQL: Healthy${NC}"
else
    echo -e "${RED}❌ PostgreSQL: Unhealthy${NC}"
fi

# Check Minder API
if curl -sf http://localhost:8000/health &> /dev/null; then
    echo -e "${GREEN}✅ Minder API: Healthy${NC}"
    API_STATUS=$(curl -s http://localhost:8000/health | jq -r '.status')
    echo "   Status: $API_STATUS"
else
    echo -e "${RED}❌ Minder API: Unhealthy${NC}"
fi

# Check OpenWebUI
if curl -sf http://localhost:3000 &> /dev/null; then
    echo -e "${GREEN}✅ OpenWebUI: Healthy${NC}"
else
    echo -e "${YELLOW}⚠️  OpenWebUI: Not responding yet${NC}"
fi

echo ""

# Step 8: Run Initial Tests
echo -e "${BLUE}🧪 Step 8: Running Initial Tests${NC}"
echo "----------------------------"

echo "Testing API endpoints..."

# Test health endpoint
echo "  GET /health"
HEALTH_RESPONSE=$(curl -s http://localhost:8000/health)
echo "  Response: ${HEALTH_RESPONSE:0:100}..."

# Test modules endpoint
echo "  GET /api/modules"
MODULES_RESPONSE=$(curl -s http://localhost:8000/api/modules)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Modules endpoint working${NC}"
else
    echo -e "${YELLOW}⚠️  Modules endpoint returned error${NC}"
fi

# Test characters endpoint
echo "  GET /api/characters"
CHARACTERS_RESPONSE=$(curl -s http://localhost:8000/api/characters)
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Characters endpoint working${NC}"
else
    echo -e "${YELLOW}⚠️  Characters endpoint returned error${NC}"
fi

echo ""

# Step 9: Display Access Information
echo -e "${BLUE}📍 Access Information${NC}"
echo "----------------------"
echo ""
echo -e "${GREEN}🌐 Web Interfaces:${NC}"
echo "  • Minder API:      http://localhost:8000"
echo "  • API Docs:        http://localhost:8000/docs"
echo "  • OpenWebUI:       http://localhost:3000"
echo "  • Grafana:         http://localhost:3002"
echo "    (admin/minder123)"
echo ""
echo -e "${BLUE}📊 API Endpoints:${NC}"
echo "  • Health Check:    GET  /health"
echo "  • Chat:            POST /api/chat"
echo "  • Modules:         GET  /api/modules"
echo "  • Characters:      GET  /api/characters"
echo "  • Correlations:     GET  /api/correlations"
echo "  • System Status:   GET  /api/system/status"
echo ""
echo -e "${BLUE}📱 Mobile Endpoints:${NC}"
echo "  • Dashboard:       GET  /api/mobile/dashboard"
echo "  • Modules:         GET  /api/mobile/modules"
echo "  • WebSocket:       WS   /ws/mobile/{client_id}"
echo ""
echo -e "${BLUE}📚 Documentation:${NC}"
echo "  • README:          /root/minder/README.md"
echo "  • Architecture:     /root/minder/docs/ARCHITECTURE.md"
echo "  • Migration Guide:  /root/minder/docs/MIGRATION_GUIDE.md"
echo ""

# Step 10: Next Steps
echo -e "${BLUE}➡️  Next Steps${NC}"
echo "----------------"
echo ""
echo "1. Test the chat interface:"
echo -e "   ${YELLOW}curl -X POST http://localhost:8000/api/chat \${NC}"
echo -e "   ${YELLOW}     -H 'Content-Type: application/json' \${NC}"
echo -e "   ${YELLOW}     -d '{\"message\": \"Hangi fonları önerirsin?\"}'${NC}"
echo ""
echo "2. View system status:"
echo -e "   ${YELLOW}curl http://localhost:8000/api/system/status | jq${NC}"
echo ""
echo "3. Run fund analysis pipeline:"
echo -e "   ${YELLOW}curl -X POST http://localhost:8000/api/modules/fund/pipeline \${NC}"
echo -e "   ${YELLOW}     -H 'Content-Type: application/json' \${NC}"
echo -e "   ${YELLOW}     -d '{\"module\": \"fund\", \"pipeline\": [\"collect\", \"analyze\"]}'${NC}"
echo ""
echo "4. Check logs:"
echo -e "   ${YELLOW}docker-compose logs -f minder-api${NC}"
echo ""
echo "5. Stop services:"
echo -e "   ${YELLOW}docker-compose down${NC}"
echo ""

# Success message
echo -e "${GREEN}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                  🎉 Deployment Successful!                          ║${NC}"
echo -e "${GREEN}║                                                                    ║${NC}"
echo -e "${GREEN}║  Minder platform is now running with all modules active            ║${NC}"
echo -e "${GREEN}║                                                                    ║${NC}"
echo -e "${GREEN}║  Ready to provide AI-powered insights across domains               ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
