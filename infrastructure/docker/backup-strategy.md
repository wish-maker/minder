# Minder Platform Backup Strategy

**Version:** 1.0.0
**Last Updated:** 2026-05-13
**Status:** 🟡 TO BE IMPLEMENTED

---

## 📊 Current Status

### Missing Backups

Currently, the Minder platform lacks an automated backup system. The following critical data needs backup strategy:

**Databases:**
- PostgreSQL: User data, sessions, metadata
- Redis: Cache, rate limiting, session state
- Neo4j: Graph relationships, entity links
- Qdrant: Vector embeddings, semantic search index
- InfluxDB: Time-series metrics, monitoring data
- RabbitMQ: Message queues, pipeline triggers

**Configuration:**
- Docker Compose files
- Environment variables (.env)
- Traefik configuration
- Authelia user database
- Plugin configurations

---

## 🎯 Backup Strategy

### Level 1: Database Backups (Daily)

#### 1.1 PostgreSQL Backup

**Frequency:** Daily at 02:00
**Retention:** 7 days
**Method:** pg_dump

```bash
#!/bin/bash
# /root/minder/scripts/backup-postgres.sh

BACKUP_DIR="/root/minder/backups/postgres"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

docker exec minder-postgres pg_dump -U postgres -d minder \
  > "$BACKUP_DIR/minder-postgres-$DATE.sql"

# Compress
gzip "$BACKUP_DIR/minder-postgres-$DATE.sql"

# Cleanup old backups (keep 7 days)
find "$BACKUP_DIR" -name "minder-postgres-*.sql.gz" -mtime +7 -delete
```

**Estimated Size:** ~1-5 MB per backup
**Retention Size:** ~35 MB (7 days)

#### 1.2 Redis Backup

**Frequency:** Daily at 02:10
**Retention:** 7 days
**Method:** Redis SAVE command + file copy

```bash
#!/bin/bash
# /root/minder/scripts/backup-redis.sh

BACKUP_DIR="/root/minder/backups/redis"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

# Trigger Redis SAVE
docker exec minder-redis redis-cli BGSAVE

# Wait for save to complete
sleep 5

# Copy dump file
docker cp minder-redis:/data/dump.rdb "$BACKUP_DIR/redis-$DATE.rdb"

# Compress
gzip "$BACKUP_DIR/redis-$DATE.rdb"

# Cleanup old backups
find "$BACKUP_DIR" -name "redis-*.rdb.gz" -mtime +7 -delete
```

**Estimated Size:** ~1-2 MB per backup
**Retention Size:** ~14 MB (7 days)

#### 1.3 Neo4j Backup

**Frequency:** Daily at 02:20
**Retention:** 7 days
**Method:** neo4j-admin backup

```bash
#!/bin/bash
# /root/minder/scripts/backup-neo4j.sh

BACKUP_DIR="/root/minder/backups/neo4j"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

docker exec -u neo4j minder-neo4j neo4j-admin backup \
  --from Graph.db --to-path "/backups/neo4j-$DATE"

# Copy backup from container
docker cp minder-neo4j:/backups/neo4j-$DATE "$BACKUP_DIR/"

# Compress
tar -czf "$BACKUP_DIR/neo4j-$DATE.tar.gz" -C "$BACKUP_DIR" "neo4j-$DATE"
rm -rf "$BACKUP_DIR/neo4j-$DATE"

# Cleanup old backups
find "$BACKUP_DIR" -name "neo4j-*.tar.gz" -mtime +7 -delete
```

**Estimated Size:** ~10-20 MB per backup
**Retention Size:** ~140 MB (7 days)

---

### Level 2: Configuration Backups (Weekly)

#### 2.1 Config Files Backup

**Frequency:** Weekly on Sunday at 03:00
**Retention:** 4 weeks
**Method:** tar + gzip

```bash
#!/bin/bash
# /root/minder/scripts/backup-config.sh

BACKUP_DIR="/root/minder/backups/config"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

# Create config backup
tar -czf "$BACKUP_DIR/minder-config-$DATE.tar.gz" \
  -C /root/minder \
  infrastructure/docker/.env \
  infrastructure/docker/traefik \
  infrastructure/docker/authelia \
  infrastructure/docker/docker-compose.yml

# Cleanup old backups (keep 4 weeks)
find "$BACKUP_DIR" -name "minder-config-*.tar.gz" -mtime +28 -delete
```

**Estimated Size:** ~1-2 MB per backup
**Retention Size:** ~8 MB (4 weeks)

---

### Level 3: System Snapshots (Monthly)

#### 3.1 Full System Snapshot

**Frequency:** Monthly on 1st at 04:00
**Retention:** 3 months
**Method:** Docker volume snapshots

```bash
#!/bin/bash
# /root/minder/scripts/backup-snapshot.sh

BACKUP_DIR="/root/minder/backups/snapshots"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p "$BACKUP_DIR"

# Stop services
cd /root/minder/infrastructure/docker
docker compose stop

# Create volume snapshots
for volume in postgres_data redis_data neo4j_data qdrant_storage influxdb_data rabbitmq_data; do
  docker run --rm -v minder_$volume:/data -v "$BACKUP_DIR":/backup \
    alpine tar -czf "/backup/$volume-$DATE.tar.gz" -C /data .
done

# Start services
docker compose start

# Cleanup old snapshots (keep 3 months)
find "$BACKUP_DIR" -name "*-*.tar.gz" -mtime +90 -delete
```

**Estimated Size:** ~100-200 MB per snapshot
**Retention Size:** ~600 MB (3 months)

---

## 📋 Implementation Plan

### Phase 1: Script Creation (Week 1)
- [ ] Create backup scripts directory
- [ ] Write PostgreSQL backup script
- [ ] Write Redis backup script
- [ ] Write Neo4j backup script
- [ ] Write configuration backup script
- [ ] Write system snapshot script
- [ ] Test all scripts manually

### Phase 2: Automation Setup (Week 2)
- [ ] Create cron jobs for daily backups
- [ ] Create cron jobs for weekly backups
- [ ] Create cron jobs for monthly snapshots
- [ ] Setup backup monitoring
- [ ] Configure failure notifications

### Phase 3: Testing & Validation (Week 3)
- [ ] Test backup restoration (PostgreSQL)
- [ ] Test backup restoration (Redis)
- [ ] Test backup restoration (Neo4j)
- [ ] Test configuration restoration
- [ ] Verify backup retention policies
- [ ] Document restore procedures

### Phase 4: Monitoring Setup (Week 4)
- [ ] Setup backup success metrics (Prometheus)
- [ ] Configure backup size alerts
- [ ] Setup backup failure notifications
- [ ] Create Grafana backup dashboard
- [ ] Document backup runbook

---

## 🔍 Backup Verification

### Weekly Verification Tasks

```bash
# 1. Check backup files exist
ls -lh /root/minder/backups/*/minder-*

# 2. Verify backup sizes
du -sh /root/minder/backups/*

# 3. Test restore (staging)
# Restore latest backup to test environment
./setup.sh restore --test postgres
./setup.sh restore --test redis
./setup.sh restore --test neo4j

# 4. Check backup logs
grep -i "backup\|error" /var/log/syslog | tail -50
```

---

## 📊 Storage Requirements

### Estimated Total Storage

**Daily Backups:** ~50 MB/day
**Weekly Config:** ~2 MB/week
**Monthly Snapshots:** ~200 MB/month

**Total Growth:** ~2-3 GB/month
**Recommended Storage:** 50 GB dedicated backup partition

---

## 🚨 Failure Handling

### Backup Failure Procedures

1. **Immediate Action:**
   - Check disk space: `df -h`
   - Check service status: `docker ps`
   - Check backup logs: `tail -f /var/log/backup.log`

2. **Retry Logic:**
   - Automatic retry after 1 hour
   - Max 3 retry attempts
   - Alert after 3rd failure

3. **Manual Intervention:**
   - Manual backup trigger: `./setup.sh backup --manual`
   - Specific service backup: `./setup.sh backup postgres`

---

## 📝 Monitoring & Alerts

### Prometheus Metrics

```yaml
# Backup success rate
backup_success_total{service="postgres"} 1
backup_success_total{service="redis"} 1
backup_success_total{service="neo4j"} 1

# Backup sizes (bytes)
backup_size_bytes{service="postgres"} 5242880
backup_size_bytes{service="redis"} 1048576
backup_size_bytes{service="neo4j"} 15728640

# Backup duration (seconds)
backup_duration_seconds{service="postgres"} 45
backup_duration_seconds{service="redis"} 10
backup_duration_seconds{service="neo4j"} 120
```

### Alert Rules

```yaml
# Alert: Backup failure
- alert: BackupFailure
  expr: backup_success_total == 0
  for: 10m
  labels:
    severity: critical
  annotations:
    summary: "Backup failed for {{ $labels.service }}"

# Alert: Backup too large
- alert: BackupSizeTooLarge
  expr: backup_size_bytes > 1073741824  # 1GB
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Backup size exceeds 1GB for {{ $labels.service }}"

# Alert: Backup taking too long
- alert: BackupDurationTooLong
  expr: backup_duration_seconds > 600  # 10 minutes
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "Backup taking too long for {{ $labels.service }}"
```

---

## ✅ Success Criteria

- [ ] All 6 databases have automated daily backups
- [ ] Configuration files backed up weekly
- [ ] System snapshots created monthly
- [ ] Backup retention policies enforced
- [ ] Backup success rate > 99%
- [ ] Backup restoration tested monthly
- [ ] Backup monitoring dashboard active
- [ ] Backup failure notifications configured

---

**Status:** 🟡 **TO BE IMPLEMENTED** - Planning phase complete, implementation pending

**Next Steps:**
1. Review and approve this strategy
2. Create backup scripts (Phase 1)
3. Setup automation (Phase 2)
4. Test restoration procedures (Phase 3)
5. Configure monitoring (Phase 4)
