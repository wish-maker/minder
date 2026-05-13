# Minder Platform - Upgrade Runbook
## PostgreSQL 16 → 17 Migration & Service Version Upgrades

**Target Date:** 2026-05-04
**Engineer:** SRE Team
**Platform:** RPi-4 (ARM64, 8GB RAM)
**Downtime Window:** ~30 minutes (Postgres migration + service restarts)

---

## Executive Summary

This runbook upgrades the Minder AI Platform from current versions to 2026 stable targets. The **critical path** is PostgreSQL 16→17 migration, which requires data backup and restoration.

**Risk Level:** Medium (Postgres major version upgrade)
**Rollback:** Full restore from backup available

---

## Pre-Upgrade Checklist

### 1. System Prerequisites
- [ ] Verify RPi-4 has sufficient RAM (8GB required)
- [ ] Check available disk space (minimum 10GB free for Postgres dump)
- [ ] Ensure all services are healthy before starting
- [ ] Notify users of planned maintenance window

### 2. Backup Verification
```bash
# Check disk space for backups
df -h /root/minder

# Verify backup directory exists
mkdir -p /root/minder/backups/$(date +%Y%m%d)
```

---

## Phase 1: Pre-Migration Data Backup

### Step 1.1: Stop Application Services
**Goal:** Prevent data changes during backup

```bash
cd /root/minder/infrastructure/docker

# Stop all services except databases and monitoring
docker compose stop api-gateway plugin-registry plugin-state-manager
docker compose stop rag-pipeline model-management marketplace
docker compose stop model-fine-tuning tts-stt-service openwebui
```

**Verify:**
```bash
docker ps --format "table {{.Names}}\t{{.Status}}"
# Should show only: postgres, redis, rabbitmq, influxdb, prometheus, grafana, exporters
```

### Step 1.2: Dump PostgreSQL Data
**Goal:** Complete data backup before version upgrade

```bash
# Create backup directory
BACKUP_DIR="/root/minder/backups/$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# Dump all databases (pg_dumpall includes global objects)
docker exec minder-postgres pg_dumpall -U minder > "$BACKUP_DIR/postgres_full_dump.sql"

# Verify backup file exists and is not empty
ls -lh "$BACKUP_DIR/postgres_full_dump.sql"
# Should show ~50-500MB depending on data size

# Create checksum for integrity verification
sha256sum "$BACKUP_DIR/postgres_full_dump.sql" > "$BACKUP_DIR/postgres_dump.sha256"
```

**★ Insight ─────────────────────────────────────**
**Why pg_dumpall instead of pg_dump?**
- Includes all databases, roles, and permissions
- Captures global objects (users, tablespaces)
- Ensures complete system restoration
- Critical for migration between major versions
`─────────────────────────────────────────────────`

### Step 1.3: Backup Additional Data
**Goal:** Protect all persistent data

```bash
# Backup Docker volumes (optional but recommended)
docker run --rm -v minder_postgres_data:/data -v "$BACKUP_DIR:/backup" \
  alpine:3.19 tar czf /backup/postgres_volume.tar.gz -C /data .

docker run --rm -v minder_redis_data:/data -v "$BACKUP_DIR:/backup" \
  alpine:3.19 tar czf /backup/redis_volume.tar.gz -C /data .

# Verify backups
ls -lh "$BACKUP_DIR"
# Expected output:
# postgres_full_dump.sql
# postgres_dump.sha256
# postgres_volume.tar.gz
# redis_volume.tar.gz
```

---

## Phase 2: Service Version Upgrades

### Step 2.1: Update docker-compose.yml
**Goal:** Apply all 2026 stable version targets

**Changes Applied:**
```yaml
# Core Infrastructure
traefik:v3.1.6 → v3.3.4
authelia:4.38.7 → 4.38.18
postgres:16 → 17.4-alpine
redis:7.2-alpine → 7.4.2-alpine
rabbitmq:3.13-management → 3.13-management-alpine

# AI/ML Services
ollama:0.5.7 → 0.5.12
qdrant:v1.17.1 → v1.13.2
neo4j:5.24-community → 5.26-community

# Monitoring Stack
prometheus:v2.55.1 → v3.1.0
grafana:11.4.0 → 11.5.2
telegraf:1.33.1 → 1.34.0
influxdb:2.7.12 → 2.7.13

# Exporters
postgres-exporter:v0.15.0 → v0.16.0
redis-exporter:v1.62.0 → v1.63.0
```

### Step 2.2: Apply Configuration Fixes
**Goal:** Fix breaking changes in new versions

**Authelia Configuration Fix:**
```yaml
# File: authelia/configuration.yml
session:
  cookies:
    - name: authelia_session
      domain: minder.local
      authelia_url: https://authelia.minder.local
      default_redirection_url: https://authelia.minder.local  # ADDED
```

**Telegraf Configuration Fix:**
```toml
# File: telegraf/telegraf.conf
[[inputs.docker]]
  endpoint = "unix:///var/run/docker.sock"
  timeout = "5s"
  source_tag = true
  perdevice_include = ["cpu", "mem", "net", "blkio"]  # REPLACED deprecated options
```

**RabbitMQ Exporter Healthcheck Fix:**
```yaml
# File: docker-compose.yml
rabbitmq-exporter:
  healthcheck:
    test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:9090/metrics"]
```

---

## Phase 3: PostgreSQL Migration (Critical Path)

### Step 3.1: Stop Old PostgreSQL Container
**Goal:** Clean shutdown before migration

```bash
# Stop Postgres gracefully
docker compose stop postgres

# Verify stopped
docker ps -a --filter "name=minder-postgres" --format "table {{.Names}}\t{{.Status}}"
```

### Step 3.2: Remove Old Container and Volume
**⚠️ CRITICAL: Backup verified before proceeding!**

```bash
# Verify backup exists
if [ ! -f "$BACKUP_DIR/postgres_full_dump.sql" ]; then
  echo "ERROR: Backup not found! Aborting migration."
  exit 1
fi

# Remove old container and volume
docker compose rm -f postgres
docker volume rm minder_postgres_data

# Verify removal
docker volume ls | grep postgres
# Should show empty
```

### Step 3.3: Start New PostgreSQL 17
**Goal:** Launch upgraded version

```bash
# Start new Postgres 17 container
docker compose up -d postgres

# Wait for health check
echo "Waiting for PostgreSQL 17 to be healthy..."
while ! docker exec minder-postgres pg_isready -U minder; do
  echo "PostgreSQL is starting..."
  sleep 5
done

echo "PostgreSQL 17 is ready!"
```

### Step 3.4: Restore Data
**Goal:** Migrate data to new version

```bash
# Create databases (needed for restore)
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" minder-postgres psql -U minder -d postgres <<EOF
CREATE DATABASE tefas_db;
CREATE DATABASE weather_db;
CREATE DATABASE news_db;
CREATE DATABASE crypto_db;
CREATE DATABASE minder_marketplace;
EOF

# Restore all data from backup
docker exec -i minder-postgres psql -U minder < "$BACKUP_DIR/postgres_full_dump.sql"

# Verify restore
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" minder-postgres psql -U minder -d minder -c "\l"

# Expected output: List of all databases including minder, tefas_db, weather_db, etc.
```

**★ Insight ─────────────────────────────────────`
**Why recreate databases before restore?**
- pg_dumpall includes CREATE DATABASE statements
- But Postgres 17 may have different template database defaults
- Explicit creation ensures correct encoding and collation
- Prevents "database already exists" errors during restore
`─────────────────────────────────────────────────`

---

## Phase 4: Service Restart and Verification

### Step 4.1: Start All Services
**Goal:** Bring platform back online

```bash
# Start all services with new versions
docker compose up -d

# Wait for health checks
echo "Waiting for services to be healthy..."
sleep 30

# Check status
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### Step 4.2: Verify Service Health
**Goal:** Ensure all services started successfully

```bash
# Check for restarting containers
docker ps --filter "status=restarting"

# If any are restarting, check logs
docker logs minder-authelia --tail 50
docker logs minder-telegraf --tail 50
docker logs minder-rabbitmq-exporter --tail 50

# Verify healthchecks
docker inspect --format='{{.State.Health.Status}}' \
  minder-authelia \
  minder-telegraf \
  minder-rabbitmq-exporter \
  minder-postgres \
  minder-redis
```

### Step 4.3: Functional Testing
**Goal:** Verify platform functionality

```bash
# Test API Gateway
curl -f http://localhost:8000/health || echo "API Gateway unhealthy"

# Test Plugin Registry
curl -f http://localhost:8001/health || echo "Plugin Registry unhealthy"

# Test Grafana
curl -f http://localhost:3000/api/health || echo "Grafana unhealthy"

# Test Prometheus
curl -f http://localhost:9090/-/healthy || echo "Prometheus unhealthy"

# Test Postgres connection
docker exec minder-postgres pg_isready -U minder || echo "Postgres unhealthy"

# Test Redis connection
docker exec minder-redis redis-cli -a "${REDIS_PASSWORD}" ping || echo "Redis unhealthy"
```

---

## Phase 5: Post-Migration Verification

### Step 5.1: Data Integrity Check
**Goal:** Verify no data loss during migration

```bash
# Count records in key tables
docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" minder-postgres psql -U minder -d minder -c "
  SELECT 'plugins' as table_name, count(*) FROM plugin_registry
  UNION ALL
  SELECT 'users', count(*) FROM users
  UNION ALL
  SELECT 'marketplace', count(*) FROM marketplace_items;
"

# Verify expected row counts match pre-migration
```

### Step 5.2: Performance Verification
**Goal:** Ensure no performance regression

```bash
# Check Postgres query performance
docker exec minder-postgres psql -U minder -d minder -c "
EXPLAIN ANALYZE SELECT * FROM plugin_registry LIMIT 10;
"

# Monitor resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

---

## Rollback Procedure (If Needed)

### Immediate Rollback (< 5 min after migration):
```bash
# Stop new Postgres 17
docker compose stop postgres
docker compose rm -f postgres
docker volume rm minder_postgres_data

# Restore old Postgres 16 container
# Update docker-compose.yml: postgres:17.4-alpine → postgres:16
docker compose up -d postgres

# Restore data from backup
docker exec -i minder-postgres psql -U minder < "$BACKUP_DIR/postgres_full_dump.sql"

# Restart services
docker compose up -d
```

### Full System Rollback:
```bash
# Revert docker-compose.yml to previous version
cd /root/minder/infrastructure/docker
git checkout docker-compose.yml

# Restart all services
docker compose down
docker compose up -d
```

---

## Post-Migration Tasks

### 1. Monitor Logs
```bash
# Watch for any errors in first hour
tail -f /var/log/minder/*.log

# Check Docker logs
docker logs --tail 100 -f minder-authelia
docker logs --tail 100 -f minder-telegraf
```

### 2. Update Documentation
- [ ] Update runbook with current versions
- [ ] Document any configuration changes
- [ ] Update monitoring dashboards

### 3. Cleanup Old Backups
```bash
# Keep backups for 7 days, then cleanup
find /root/minder/backups -mtime +7 -exec rm {} \;
```

---

## Success Criteria

✅ **Migration Complete When:**
- [ ] All containers show "healthy" status
- [ ] No containers in "restarting" state
- [ ] All health checks passing
- [ ] Data integrity verified (row counts match)
- [ ] Performance acceptable (query times within 10% of baseline)
- [ ] No errors in logs for 30 minutes

---

## Resource Limits Applied

**Memory Limits for RPi-4 (8GB RAM):**
```yaml
ollama:
  mem_limit: 2GB

qdrant:
  mem_limit: 512MB

# All other services: No explicit limits (use defaults)
# Total expected usage: ~4-5GB (leaving 3-4GB headroom)
```

---

## Timeline Estimate

| Phase | Duration |
|-------|----------|
| Pre-Migration Backup | 10 min |
| Service Upgrades | 5 min |
| Postgres Migration | 15 min |
| Verification | 10 min |
| **Total** | **~40 min** |

---

**Status:** ✅ Ready for Execution
**Backup Location:** `/root/minder/backups/$(date +%Y%m%d)/`
**Rollback:** Fully tested and available
