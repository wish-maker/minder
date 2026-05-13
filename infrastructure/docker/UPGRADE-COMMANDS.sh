#!/bin/bash
# ============================================================================
# Minder Platform - Quick Upgrade Commands
# ============================================================================
# Execute this script to perform the complete upgrade with backups
# ============================================================================

set -e  # Exit on error
set -u  # Exit on undefined variable

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# PRE-UPGRADE CHECKS
# ============================================================================

log_info "Starting pre-upgrade checks..."

# Check available disk space
AVAILABLE_SPACE=$(df -BG /root/minder | awk 'NR==2 {print $4}' | sed 's/G//')
if [ "$AVAILABLE_SPACE" -lt 10 ]; then
    log_error "Insufficient disk space. Need at least 10GB free."
    exit 1
fi
log_info "Disk space check passed: ${AVAILABLE_SPACE}GB available"

# Check if all services are healthy
UNHEALTHY=$(docker ps --filter "name=minder" --filter "status=running" --format "{{.Names}}" | \
    xargs -I {} docker inspect --format='{{.State.Health.Status}}' {} 2>/dev/null | \
    grep -c "unhealthy" || echo "0")

if [ "$UNHEALTHY" -gt 0 ]; then
    log_warn "Found $UNHEALTHY unhealthy services. Consider fixing before upgrade."
fi

# ============================================================================
# PHASE 1: BACKUP
# ============================================================================

log_info "=== Phase 1: Creating Backups ==="

BACKUP_DIR="/root/minder/backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

log_info "Stopping application services..."
cd /root/minder/infrastructure/docker
docker compose stop api-gateway plugin-registry plugin-state-manager \
    rag-pipeline model-management marketplace \
    model-fine-tuning tts-stt-service openwebui

log_info "Dumping PostgreSQL database..."
docker exec minder-postgres pg_dumpall -U minder > "$BACKUP_DIR/postgres_full_dump.sql"

if [ ! -s "$BACKUP_DIR/postgres_full_dump.sql" ]; then
    log_error "PostgreSQL dump failed or is empty!"
    exit 1
fi

log_info "Creating checksum..."
sha256sum "$BACKUP_DIR/postgres_full_dump.sql" > "$BACKUP_DIR/postgres_dump.sha256"

BACKUP_SIZE=$(du -h "$BACKUP_DIR/postgres_full_dump.sql" | cut -f1)
log_info "Backup created successfully: $BACKUP_DIR/postgres_full_dump.sql ($BACKUP_SIZE)"

# ============================================================================
# PHASE 2: UPGRADE SERVICES
# ============================================================================

log_info "=== Phase 2: Upgrading Services ==="

log_info "Pulling new images..."
docker compose pull

log_info "Stopping old PostgreSQL container..."
docker compose stop postgres
docker compose rm -f postgres

log_info "Removing old PostgreSQL volume..."
docker volume rm minder_postgres_data

# ============================================================================
# PHASE 3: MIGRATE POSTGRES
# ============================================================================

log_info "=== Phase 3: PostgreSQL Migration ==="

log_info "Starting new PostgreSQL 17..."
docker compose up -d postgres

log_info "Waiting for PostgreSQL to be ready..."
sleep 10
for i in {1..30}; do
    if docker exec minder-postgres pg_isready -U minder >/dev/null 2>&1; then
        log_info "PostgreSQL is ready!"
        break
    fi
    if [ $i -eq 30 ]; then
        log_error "PostgreSQL failed to start within 30 seconds"
        exit 1
    fi
    sleep 2
done

log_info "Creating databases..."
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" minder-postgres psql -U minder -d postgres <<EOF
CREATE DATABASE tefas_db;
CREATE DATABASE weather_db;
CREATE DATABASE news_db;
CREATE DATABASE crypto_db;
CREATE DATABASE minder_marketplace;
EOF

log_info "Restoring data from backup..."
docker exec -i minder-postgres psql -U minder < "$BACKUP_DIR/postgres_full_dump.sql"

# ============================================================================
# PHASE 4: RESTART ALL SERVICES
# ============================================================================

log_info "=== Phase 4: Restarting All Services ==="

log_info "Starting all services with new versions..."
docker compose up -d

log_info "Waiting for services to initialize..."
sleep 30

# ============================================================================
# PHASE 5: VERIFICATION
# ============================================================================

log_info "=== Phase 5: Verifying Upgrade ==="

# Check for unhealthy containers
UNHEALTHY_SERVICES=$(docker ps --filter "name=minder" --format "{{.Names}}\t{{.State.Health.Status}}" | \
    grep -c "unhealthy" || echo "0")

if [ "$UNHEALTHY_SERVICES" -gt 0 ]; then
    log_warn "Found $UNHEALTHY_SERVICES unhealthy services:"
    docker ps --filter "name=minder" --format "{{.Names}}\t{{.State.Health.Status}}" | grep "unhealthy"
    log_warn "Check logs with: docker logs <container-name>"
fi

# Test critical endpoints
log_info "Testing critical endpoints..."

test_endpoint() {
    local url=$1
    local name=$2
    if curl -sf "$url" >/dev/null 2>&1; then
        log_info "✓ $name is responding"
        return 0
    else
        log_error "✗ $name is not responding"
        return 1
    fi
}

FAILED_CHECKS=0
test_endpoint "http://localhost:8000/health" "API Gateway" || ((FAILED_CHECKS++))
test_endpoint "http://localhost:3000/api/health" "Grafana" || ((FAILED_CHECKS++))
test_endpoint "http://localhost:9090/-/healthy" "Prometheus" || ((FAILED_CHECKS++))

# Test databases
if docker exec minder-postgres pg_isready -U minder >/dev/null 2>&1; then
    log_info "✓ PostgreSQL is ready"
else
    log_error "✗ PostgreSQL is not ready"
    ((FAILED_CHECKS++))
fi

if docker exec minder-redis redis-cli -a "${REDIS_PASSWORD}" ping >/dev/null 2>&1; then
    log_info "✓ Redis is responding"
else
    log_error "✗ Redis is not responding"
    ((FAILED_CHECKS++))
fi

# ============================================================================
# SUMMARY
# ============================================================================

echo ""
log_info "=== Upgrade Summary ==="
log_info "Backup location: $BACKUP_DIR"
log_info "Failed health checks: $FAILED_CHECKS"

if [ "$FAILED_CHECKS" -eq 0 ]; then
    log_info "✓ Upgrade completed successfully!"
    echo ""
    log_info "Next steps:"
    log_info "1. Monitor logs: docker logs -f minder-authelia minder-telegraf"
    log_info "2. Check Grafana dashboards: http://localhost:3000"
    log_info "3. Verify application functionality"
else
    log_error "Upgrade completed with $FAILED_CHECKS failed checks"
    log_error "Check logs above for details"
    log_error "To rollback: See UPGRADE-RUNBOOK.md"
    exit 1
fi

# Display resource usage
log_info "Current resource usage:"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | \
    grep -E "NAME|ollama|qdrant|postgres" || true

echo ""
log_info "=== Upgrade Complete ==="
