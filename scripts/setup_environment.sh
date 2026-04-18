#!/bin/bash
#
# Minder Environment Setup Script
# Initial setup for new Minder installations
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
echo "MINDER ENVIRONMENT SETUP"
echo "=================================================="

# ============================================
# 1. Check Prerequisites
# ============================================
echo ""
echo "1. Checking prerequisites..."
echo "----------------------------"

# Check Docker
if ! command -v docker &> /dev/null; then
    print_status "FAILED" "Docker not installed"
    exit 1
fi
print_status "SUCCESS" "Docker installed: $(docker --version)"

# Check Docker Compose
if ! command -v docker &> /dev/null || ! docker compose version &> /dev/null; then
    print_status "FAILED" "Docker Compose not installed"
    exit 1
fi
print_status "SUCCESS" "Docker Compose installed: $(docker compose version)"

# Check required ports
PORTS=(5432 8086 6333 6379 8000)
OCCUPIED_PORTS=()

for port in "${PORTS[@]}"; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        OCCUPIED_PORTS+=($port)
    fi
done

if [ ${#OCCUPIED_PORTS[@]} -gt 0 ]; then
    print_status "WARNING" "Ports already in use: ${OCCUPIED_PORTS[*]}"
    echo "  This may cause conflicts with Minder containers"
fi

# ============================================
# 2. Create Directory Structure
# ============================================
echo ""
echo "2. Creating directory structure..."
echo "----------------------------"

DIRS=(
    "/var/backups/minder"
    "/var/log/minder"
    "./scripts"
    "./data"
)

for dir in "${DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        print_status "SUCCESS" "Created directory: $dir"
    else
        echo "  - Directory exists: $dir"
    fi
done

# ============================================
# 3. Check .env File
# ============================================
echo ""
echo "3. Checking environment configuration..."
echo "----------------------------"

if [ ! -f .env ]; then
    print_status "WARNING" ".env file not found"

    if [ -f .env.example ]; then
        print_status "INFO" "Found .env.example, copying to .env"
        cp .env.example .env
        print_status "SUCCESS" "Created .env from .env.example"
        print_status "WARNING" "Please edit .env and set strong passwords!"
    else
        print_status "INFO" "Creating minimal .env file"

        cat > .env << 'EOF'
# PostgreSQL Configuration
POSTGRES_PASSWORD=postgrespassword

# InfluxDB Configuration
INFLUXDB_INIT_PASSWORD=minderpassword
INFLUXDB_INIT_USERNAME=minder
INFLUXDB_INIT_ORG=minder
INFLUXDB_INIT_BUCKET=metrics

# JWT Configuration
JWT_SECRET_KEY=this_must_be_at_least_32_characters_long_for_security
JWT_EXPIRE_MINUTES=30

# Environment
ENVIRONMENT=development

# Allowed origins for API
ALLOWED_ORIGINS=http://localhost:3000,http://192.168.68.*
EOF

        print_status "SUCCESS" "Created .env with default values"
        print_status "WARNING" "Please update .env with production-ready values!"
    fi
else
    print_status "SUCCESS" ".env file exists"
fi

# ============================================
# 4. Verify Secrets Strength
# ============================================
echo ""
echo "4. Verifying secrets strength..."
echo "----------------------------"

# Check JWT secret
JWT_SECRET=$(grep "^JWT_SECRET_KEY=" .env | cut -d'=' -f2)
if [ ${#JWT_SECRET} -lt 32 ]; then
    print_status "WARNING" "JWT_SECRET_KEY is too short (min 32 chars)"
    echo "  Current length: ${#JWT_SECRET} characters"
else
    print_status "SUCCESS" "JWT_SECRET_KEY length: ${#JWT_SECRET} characters"
fi

# Check PostgreSQL password
POSTGRES_PASSWORD=$(grep "^POSTGRES_PASSWORD=" .env | cut -d'=' -f2)
if [ ${#POSTGRES_PASSWORD} -lt 12 ]; then
    print_status "WARNING" "POSTGRES_PASSWORD is weak (min 12 chars)"
else
    print_status "SUCCESS" "POSTGRES_PASSWORD length: ${#POSTGRES_PASSWORD} characters"
fi

# ============================================
# 5. Initialize Databases
# ============================================
echo ""
echo "5. Initializing databases..."
echo "----------------------------"

# Start containers if not running
if ! docker ps | grep -q "minder-api"; then
    print_status "INFO" "Starting Minder containers..."
    docker compose up -d

    print_status "INFO" "Waiting for containers to be ready..."
    sleep 30
fi

# Check PostgreSQL
if docker exec postgres pg_isready -U postgres &> /dev/null; then
    print_status "SUCCESS" "PostgreSQL is ready"
else
    print_status "FAILED" "PostgreSQL is not ready"
fi

# Check InfluxDB
if docker exec influxdb influx ping &> /dev/null; then
    print_status "SUCCESS" "InfluxDB is ready"
else
    print_status "WARNING" "InfluxDB may not be ready"
fi

# Check Qdrant
if docker exec qdrant curl -s http://localhost:6333/health &> /dev/null; then
    print_status "SUCCESS" "Qdrant is ready"
else
    print_status "WARNING" "Qdrant may not be ready"
fi

# Check Redis
if docker exec redis redis-cli ping &> /dev/null; then
    print_status "SUCCESS" "Redis is ready"
else
    print_status "WARNING" "Redis may not be ready"
fi

# ============================================
# 6. Setup Backup Cron Job
# ============================================
echo ""
echo "6. Setting up automated backups..."
echo "----------------------------"

BACKUP_SCRIPT="./scripts/backup_databases.sh"

if [ -f "$BACKUP_SCRIPT" ]; then
    chmod +x "$BACKUP_SCRIPT"

    # Check if cron job exists
    CRON_JOB="0 2 * * * $BACKUP_SCRIPT >> /var/log/minder/backup.log 2>&1"

    if ! crontab -l 2>/dev/null | grep -q "$BACKUP_SCRIPT"; then
        print_status "INFO" "Adding cron job for daily backups at 2:00 AM"
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        print_status "SUCCESS" "Cron job added"
    else
        print_status "SUCCESS" "Cron job already exists"
    fi
else
    print_status "WARNING" "Backup script not found: $BACKUP_SCRIPT"
fi

# ============================================
# 7. Setup Cleanup Cron Job
# ============================================
echo ""
echo "7. Setting up automated cleanup..."
echo "----------------------------"

CLEANUP_SCRIPT="./scripts/cleanup_old_data.sh"

if [ -f "$CLEANUP_SCRIPT" ]; then
    chmod +x "$CLEANUP_SCRIPT"

    # Check if cron job exists
    CRON_JOB="0 3 * * 0 $CLEANUP_SCRIPT >> /var/log/minder/cleanup.log 2>&1"

    if ! crontab -l 2>/dev/null | grep -q "$CLEANUP_SCRIPT"; then
        print_status "INFO" "Adding cron job for weekly cleanup (Sundays at 3:00 AM)"
        (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
        print_status "SUCCESS" "Cron job added"
    else
        print_status "SUCCESS" "Cron job already exists"
    fi
else
    print_status "WARNING" "Cleanup script not found: $CLEANUP_SCRIPT"
fi

# ============================================
# 8. Create Initial Backup
# ============================================
echo ""
echo "8. Creating initial backup..."
echo "----------------------------"

if [ -f "$BACKUP_SCRIPT" ]; then
    print_status "INFO" "Running initial backup..."
    if bash "$BACKUP_SCRIPT"; then
        print_status "SUCCESS" "Initial backup completed"
    else
        print_status "FAILED" "Initial backup failed"
    fi
else
    print_status "WARNING" "Skipping backup (script not found)"
fi

# ============================================
# 9. Test API Endpoint
# ============================================
echo ""
echo "9. Testing API endpoint..."
echo "----------------------------"

sleep 5  # Give API time to start

if curl -s http://localhost:8000/health | grep -q "healthy"; then
    print_status "SUCCESS" "API is responding"
else
    print_status "WARNING" "API may not be ready yet"
    echo "  Check with: docker logs minder-api"
fi

# ============================================
# Summary
# ============================================
echo ""
echo "=================================================="
print_status "SUCCESS" "Minder environment setup completed!"
echo "=================================================="
echo ""
echo "Next steps:"
echo "  1. Update .env with production-ready passwords"
echo "  2. Configure reverse proxy (nginx) for HTTPS"
echo "  3. Review and adjust resource limits in docker-compose.yml"
echo "  4. Install additional plugins via: POST /plugins/store/install"
echo "  5. Monitor system health: GET /system/status"
echo ""
echo "Useful commands:"
echo "  - View logs: docker logs -f minder-api"
echo "  - Restart: docker compose restart"
echo "  - Stop: docker compose down"
echo "  - Backup: ./scripts/backup_databases.sh"
echo "  - Restore: ./scripts/restore_databases.sh"
echo ""
echo "Documentation: https://github.com/wish-maker/minder"
echo "=================================================="
