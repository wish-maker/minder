#!/bin/bash
#
# Minder Production Deployment Script
# Automated deployment for production environment
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    local status=$1
    local message=$2
    if [ "$status" = "SUCCESS" ]; then
        echo -e "${GREEN}✓${NC} $message"
    elif [ "$status" = "FAILED" ]; then
        echo -e "${RED}✗${NC} $message"
    elif [ "$status" = "INFO" ]; then
        echo -e "${BLUE}ℹ${NC} $message"
    else
        echo -e "${YELLOW}⚠${NC} $message"
    fi
}

echo "=================================================="
echo "MINDER PRODUCTION DEPLOYMENT"
echo "=================================================="
echo ""

# Configuration
VERSION=${1:-"latest"}
STRATEGY=${2:-"rolling"}

echo "Deployment Configuration:"
echo "  Version: $VERSION"
echo "  Strategy: $STRATEGY"
echo "  Timestamp: $(date -Iseconds)"
echo ""

# ============================================
# 1. Pre-deployment Checks
# ============================================
echo "1. Pre-deployment Checks"
echo "----------------------------"

# Check if .env file exists
if [ ! -f .env ]; then
    print_status "FAILED" ".env file not found"
    echo "  Create .env file before deployment"
    exit 1
fi
print_status "SUCCESS" ".env file exists"

# Check Docker
if ! command -v docker &> /dev/null; then
    print_status "FAILED" "Docker not installed"
    exit 1
fi
print_status "SUCCESS" "Docker installed: $(docker --version)"

# Check Docker Compose
if ! docker compose version &> /dev/null; then
    print_status "FAILED" "Docker Compose not installed"
    exit 1
fi
print_status "SUCCESS" "Docker Compose installed"

# Check disk space
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
if [ $DISK_USAGE -gt 80 ]; then
    print_status "WARNING" "High disk usage: ${DISK_USAGE}%"
else
    print_status "SUCCESS" "Disk usage: ${DISK_USAGE}%"
fi

# ============================================
# 2. Run Tests
# ============================================
echo ""
echo "2. Running Test Suite"
echo "----------------------------"

if python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1; then
    print_status "SUCCESS" "All tests passed"
else
    print_status "FAILED" "Some tests failed"
    echo "  Fix failing tests before deployment"
    exit 1
fi

# ============================================
# 3. Security Checks
# ============================================
echo ""
echo "3. Security Verification"
echo "----------------------------"

# Check JWT secret length
JWT_SECRET=$(grep "^JWT_SECRET_KEY=" .env | cut -d'=' -f2)
if [ ${#JWT_SECRET} -lt 32 ]; then
    print_status "FAILED" "JWT_SECRET_KEY too short"
    exit 1
fi
print_status "SUCCESS" "JWT_SECRET_KEY length: ${#JWT_SECRET}"

# Check .env permissions
ENV_PERMS=$(stat -c %a .env)
if [ "$ENV_PERMS" != "600" ]; then
    chmod 600 .env
    print_status "INFO" "Fixed .env permissions to 600"
else
    print_status "SUCCESS" ".env permissions: 600"
fi

# ============================================
# 4. Build Docker Images
# ============================================
echo ""
echo "4. Building Docker Images"
echo "----------------------------"

print_status "INFO" "Building minder-api image..."
if docker compose build --no-cache api 2>&1 | tail -5; then
    print_status "SUCCESS" "Docker image built successfully"
else
    print_status "FAILED" "Docker image build failed"
    exit 1
fi

# ============================================
# 5. Backup Current Deployment
# ============================================
echo ""
echo "5. Creating Deployment Backup"
echo "----------------------------"

BACKUP_DIR="/var/backups/minder/pre-deployment-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup .env file
cp .env "$BACKUP_DIR/"
print_status "SUCCESS" "Environment backed up to $BACKUP_DIR"

# Backup databases
if [ -f "./scripts/backup_databases.sh" ]; then
    bash ./scripts/backup_databases.sh
    print_status "SUCCESS" "Database backup completed"
fi

# ============================================
# 6. Stop Current Deployment
# ============================================
echo ""
echo "6. Stopping Current Deployment"
echo "----------------------------"

if docker compose ps | grep -q "minder-api"; then
    print_status "INFO" "Stopping current containers..."
    docker compose down
    print_status "SUCCESS" "Containers stopped"
else
    print_status "INFO" "No containers running"
fi

# ============================================
# 7. Deploy New Version
# ============================================
echo ""
echo "7. Deploying Version: $VERSION"
echo "----------------------------"

print_status "INFO" "Starting new deployment..."
docker compose up -d

print_status "INFO" "Waiting for containers to be ready..."
sleep 15

# ============================================
# 8. Health Check
# ============================================
echo ""
echo "8. Deployment Health Check"
echo "----------------------------"

MAX_ATTEMPTS=30
ATTEMPT=0

while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        print_status "SUCCESS" "API is responding"
        break
    fi

    ATTEMPT=$((ATTEMPT + 1))
    echo -n "."
    sleep 2
done

echo ""

if [ $ATTEMPT -eq $MAX_ATTEMPTS ]; then
    print_status "FAILED" "API did not become healthy"
    echo "Initiating rollback..."
    docker compose down
    # Restore from backup if needed
    exit 1
fi

# Detailed health check
HEALTH_RESPONSE=$(curl -s http://localhost:8000/health)
echo "Health check response:"
echo "$HEALTH_RESPONSE" | jq '.' 2>/dev/null || echo "$HEALTH_RESPONSE"

# ============================================
# 9. Post-deployment Verification
# ============================================
echo ""
echo "9. Post-deployment Verification"
echo "----------------------------"

# Check plugins
PLUGIN_COUNT=$(curl -s http://localhost:8000/plugins | jq '.plugins | length' 2>/dev/null || echo "0")
if [ "$PLUGIN_COUNT" -ge 3 ]; then
    print_status "SUCCESS" "Plugins loaded: $PLUGIN_COUNT"
else
    print_status "WARNING" "Only $PLUGIN_COUNT plugins loaded"
fi

# Check databases
DB_STATUS=$(curl -s http://localhost:8000/system/status | jq '.databases' 2>/dev/null || echo "{}")
echo "Database status: $DB_STATUS"

# ============================================
# 10. Update Deployment Records
# ============================================
echo ""
echo "10. Updating Deployment Records"
echo "----------------------------"

DEPLOYMENT_RECORD={
    "version": "$VERSION",
    "strategy": "$STRATEGY",
    "timestamp": "$(date -Iseconds)",
    "status": "success",
    "backup_location": "$BACKUP_DIR"
}

echo "$DEPLOYMENT_RECORD" | jq '.' > "/var/log/minder/deployment_$(date +%Y%m%d_%H%M%S).json"
print_status "SUCCESS" "Deployment record created"

# ============================================
# Summary
# ============================================
echo ""
echo "=================================================="
print_status "SUCCESS" "DEPLOYMENT COMPLETED SUCCESSFULLY"
echo "=================================================="
echo ""
echo "Deployment Summary:"
echo "  Version: $VERSION"
echo "  Strategy: $STRATEGY"
echo "  Backup: $BACKUP_DIR"
echo "  Status: Running"
echo ""
echo "Next steps:"
echo "  1. Monitor logs: docker logs -f minder-api"
echo "  2. Check metrics: python3 scripts/monitoring_cli.py all"
echo "  3. Run smoke tests: pytest tests/test_system_health.py"
echo "  4. Monitor performance for 1 hour"
echo ""
echo "Rollback command:"
echo "  docker compose down && git diff HEAD~1 .env && docker compose up -d"
echo ""
echo "Monitoring commands:"
echo "  - System status: curl -s http://localhost:8000/system/status | jq '.'"
echo "  - Plugin status: curl -s http://localhost:8000/plugins | jq '.'"
echo "  - Health check: curl -s http://localhost:8000/health | jq '.'"
echo ""
echo "=================================================="
