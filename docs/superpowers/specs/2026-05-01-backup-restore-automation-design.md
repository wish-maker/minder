# Backup/Restore Automation Design

**Date:** 2026-05-01
**Priority:** CRITICAL - Data loss risk
**Status:** Design Phase

## Problem Statement

Minder Platform has **no automated backup/restore system**. Current state:
- ❌ No automated database backups
- ❌ No restore procedures
- ❌ No disaster recovery plan
- ❌ No backup retention policy
- ❌ No backup validation

**Risk**: Complete data loss with no recovery path.

## Proposed Solution: Comprehensive Backup System

### Architecture

```
minder/
└── scripts/
    ├── backup.sh                    # NEW: Main backup script
    ├── restore.sh                   # NEW: Main restore script
    ├── backup-cron.sh               # NEW: Scheduled backups
    └── backup-verify.sh             # NEW: Validate backups

backups/                             # NEW: Backup storage (gitignored)
    ├── db/                          # Database backups
    │   ├── daily/                    # Daily backups (7-day retention)
    │   ├── weekly/                   # Weekly backups (4-week retention)
    │   └── monthly/                  # Monthly backups (12-month retention)
    ├── configs/                     # Configuration backups
    │   └── .env.timestamp
    └── logs/                        # Backup logs
        └── backup.log
```

### Components

#### 1. Database Backup (PostgreSQL)

**Backup Strategy:**
- **Physical backups** - `pg_dump` for SQL dumps
- **Continuous archiving** - WAL shipping for point-in-time recovery
- **Incremental backups** - Only changed data (weekly)

**Backup Script (`scripts/backup.sh`):**
```bash
#!/bin/bash
# Minder Platform - Automated Backup Script

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/root/minder/backups/db"
RETENTION_DAYS=30

# 1. Pre-backup checks
check_database_health() {
    docker exec minder-postgres pg_isready -U minder
}

# 2. Backup all databases
backup_databases() {
    for db in minder tefas_db weather_db news_db crypto_db minder_marketplace; do
        docker exec minder-postgres pg_dump -U minder $db \
            | gzip > "$BACKUP_DIR/daily/${db}_${TIMESTAMP}.sql.gz"
    done
}

# 3. Backup Qdrant (vector DB)
backup_qdrant() {
    # Snapshot Qdrant storage
    docker exec minder-qdrant \
        curl -X POST http://localhost:6333/collections/snapshot
}

# 4. Backup configurations
backup_configs() {
    cp /root/minder/infrastructure/docker/.env \
       "/root/minder/backups/configs/.env.$TIMESTAMP"
}

# 5. Verify backups
verify_backups() {
    for backup in "$BACKUP_DIR/daily/"*_${TIMESTAMP}.sql.gz; do
        if ! zcat "$backup" | head -1 | grep -q "PostgreSQL database dump"; then
            echo "❌ Backup verification failed: $backup"
            exit 1
        fi
    done
}

# 6. Cleanup old backups
cleanup_old_backups() {
    find "$BACKUP_DIR/daily" -mtime +$RETENTION_DAYS -delete
}

# 7. Backup health check
backup_health_check() {
    # Verify backup completed successfully
    # Verify backup size is reasonable
    # Log backup metrics
}

# 8. Notification (optional)
notify_backup_status() {
    # Send email/webhook on backup completion
}
```

#### 2. Automated Scheduling

**Cron Jobs (`scripts/backup-cron.sh`):**
```bash
# Daily backups at 2 AM
0 2 * * * /root/minder/scripts/backup.sh daily

# Weekly full backups on Sunday at 3 AM
0 3 * * 0 /root/minder/scripts/backup.sh weekly

# Monthly archives on 1st at 4 AM
0 4 1 * * /root/minder/scripts/backup.sh monthly
```

#### 3. Restore Procedures

**Restore Script (`scripts/restore.sh`):**
```bash
#!/bin/bash
# Minder Platform - Automated Restore Script

BACKUP_FILE=$1
DATABASE=${2:-minder}

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: ./restore.sh <backup_file> [database]"
    exit 1
fi

# 1. Pre-restore checks
check_backup_exists() {
    if [ ! -f "$BACKUP_FILE" ]; then
        echo "❌ Backup file not found: $BACKUP_FILE"
        exit 1
    fi
}

# 2. Stop services (optional)
stop_services() {
    docker compose -f infrastructure/docker/docker-compose.yml stop
}

# 3. Create pre-restore backup
create_pre_restore_backup() {
    ./scripts/backup.sh pre-restore
}

# 4. Restore database
restore_database() {
    gunzip -c "$BACKUP_FILE" | \
    docker exec -i minder-postgres psql -U minder -d $DATABASE
}

# 5. Verify restore
verify_restore() {
    docker exec minder-postgres psql -U minder -d $DATABASE \
        -c "SELECT COUNT(*) FROM information_schema.tables"
}

# 6. Start services
start_services() {
    docker compose -f infrastructure/docker/docker-compose.yml start
}

# 7. Health check
health_check() {
    ./scripts/health-check.sh
}
```

### Data Flow

```
Scheduled Backup (Cron)
    ↓
Stop services (optional)
    ↓
Create database dump
    ↓
Compress and encrypt
    ↓
Upload to backup storage
    ↓
Verify backup integrity
    ↓
Cleanup old backups
    ↓
Send notification
```

### Backup Retention Policy

| Backup Type | Frequency | Retention | Storage Location |
|-------------|-----------|-----------|------------------|
| Daily | 2 AM | 7 days | `backups/db/daily/` |
| Weekly | Sunday 3 AM | 4 weeks | `backups/db/weekly/` |
| Monthly | 1st 4 AM | 12 months | `backups/db/monthly/` |
| Pre-deployment | Before deploy | 3 deploys | `backups/db/pre-deploy/` |

### Disaster Recovery Scenarios

#### Scenario 1: Single Database Corruption
```bash
# Stop services
docker compose stop

# Restore specific database
./scripts/restore.sh backups/db/daily/minder_20260501_020000.sql.gz minder

# Start services
docker compose start

# Verify
curl http://localhost:8000/health
```

#### Scenario 2: Complete Data Loss
```bash
# Restore all databases
for db in minder tefas_db weather_db news_db crypto_db minder_marketplace; do
    ./scripts/restore.sh backups/db/latest_${db}.sql.gz $db
done

# Restore configurations
cp backups/configs/.env.latest infrastructure/docker/.env

# Restart entire platform
./setup.sh
```

#### Scenario 3: Point-in-Time Recovery
```bash
# Use PostgreSQL WAL archives
# (Requires continuous archiving setup)
docker exec minder-postgres \
    pg_basebackup -D /var/lib/postgresql/data \
    -R -W -P -x stream
```

### Error Handling

#### Backup Failures
- **Retry logic** - 3 retries with exponential backoff
- **Fallback** - Alert on failure, keep last known good backup
- **Validation** - Verify backup file isn't corrupt

#### Restore Failures
- **Pre-restore backup** - Always backup before restore
- **Rollback** - If restore fails, restore from pre-restore backup
- **Partial restore** - Allow single database restore

### Testing Strategy

1. **Daily backup verification** - Verify backup file integrity
2. **Weekly restore test** - Restore to test environment
3. **Monthly disaster recovery drill** - Full restore simulation
4. **Quarterly backup audit** - Review retention policy

### Monitoring & Alerting

**Metrics to Track:**
- Backup success/failure rate
- Backup size trends
- Backup duration
- Restore success rate
- Disk space usage

**Alerts:**
- ❌ Backup failed
- ⚠️ Backup size too small (possible corruption)
- ⚠️ Backup disk space > 80% full
- ❌ Restore test failed

### Success Criteria

✅ Automated daily backups running
✅ Backups verified for integrity
✅ Restore procedures tested monthly
✅ Disaster recovery run quarterly
✅ Zero data loss in production

### Estimated Timeline

- **Backup script**: 4 hours
- **Restore script**: 3 hours
- **Cron setup**: 1 hour
- **Testing**: 4 hours
- **Documentation**: 2 hours

**Total**: 14 hours (2 days)

### Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Backup disk fills up | HIGH | Automated cleanup, monitoring |
| Backup corrupt silently | CRITICAL | Verification after each backup |
| Restore fails when needed | CRITICAL | Monthly restore tests |
| Backup performance impact | MEDIUM | Run during low-traffic hours |
| Lost backup encryption key | HIGH | Secure key storage, recovery process |

---

## Approval Required

Before implementing:
1. ✅ Confirm backup retention policy (7/30/365 days)
2. ✅ Confirm backup location (local vs cloud)
3. ✅ Confirm backup encryption requirements
4. ✅ Confirm testing frequency (weekly/monthly)

**Next Steps:** Upon approval, proceed to implementation plan.
