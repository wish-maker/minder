# PostgreSQL 16 → 17 Migration Guide

## ⚠️ CRITICAL WARNING

**This migration involves potential data loss. Do not proceed without:**
1. Complete backup of all databases
2. Testing in non-production environment
3. Scheduled maintenance window
4. Rollback plan prepared

---

## 📋 Pre-Migration Checklist

- [ ] Full database backup created
- [ ] Application stopped
- [ ] Backup verified (can restore)
- [ ] Maintenance window scheduled (30 min)
- [ ] Team notified of downtime
- [ ] Rollback procedure tested

---

## 🔍 Pre-Migration Analysis

### Current State
- **PostgreSQL Version:** 16.x
- **Databases:** minder, tefas_db, weather_db, news_db, crypto_db
- **Data Size:** ~2GB (estimated)
- **Extensions:** None custom

### Target State
- **PostgreSQL Version:** 17.2
- **Breaking Changes:** Catalog format changes
- **Migration Risk:** HIGH
- **Downtime:** 15-30 minutes

---

## 💾 Step 1: Create Comprehensive Backup

```bash
#!/bin/bash
# Backup PostgreSQL 16 before migration

echo "=== PostgreSQL 16 Backup ==="
echo "Starting backup process..."

# Stop all services
./setup.sh stop

# Create backup directory
BACKUP_DIR="/tmp/postgres-migration-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Dump all databases
echo "Dumping all databases..."
docker exec minder-postgres pg_dumpall -U minder > "$BACKUP_DIR/full_backup.sql"

# Backup data directory
echo "Backing up data directory..."
docker run --rm \
  -v docker_postgres_data:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar czf /backup/postgres_data.tar.gz -C /data .

# Verify backup
echo "Verifying backup..."
if [ -s "$BACKUP_DIR/full_backup.sql" ] && [ -s "$BACKUP_DIR/postgres_data.tar.gz" ]; then
    echo "✅ Backup successful!"
    echo "Backup location: $BACKUP_DIR"
    ls -lh "$BACKUP_DIR"
else
    echo "❌ Backup failed!"
    exit 1
fi
```

---

## 🔄 Step 2: Migration Procedure

```bash
#!/bin/bash
# Migrate PostgreSQL 16 → 17

BACKUP_DIR="$1"  # Pass backup directory as argument

if [ -z "$BACKUP_DIR" ]; then
    echo "❌ Error: Backup directory required"
    echo "Usage: $0 <backup_directory>"
    exit 1
fi

echo "=== PostgreSQL Migration 16 → 17 ==="
echo "Backup directory: $BACKUP_DIR"
echo ""

# Verify backup exists
if [ ! -f "$BACKUP_DIR/full_backup.sql" ]; then
    echo "❌ Error: Backup file not found!"
    exit 1
fi

# Update docker-compose.yml to use PostgreSQL 17
echo "Updating docker-compose.yml..."
sed -i 's/postgres:16/postgres:17.2/g' infrastructure/docker/docker-compose.yml

# Remove old volume (WARNING: Irreversible!)
echo "Removing old PostgreSQL 16 volume..."
docker volume rm docker_postgres_data

# Start PostgreSQL 17
echo "Starting PostgreSQL 17..."
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL 17 to start..."
sleep 30

# Verify PostgreSQL 17 is running
docker exec minder-postgres psql -U minder -c "SELECT version();"

# Restore databases
echo "Restoring databases from backup..."
cat "$BACKUP_DIR/full_backup.sql" | docker exec -i minder-postgres psql -U minder

# Verify data integrity
echo "Verifying data integrity..."
docker exec minder-postgres psql -U minder -l
docker exec minder-postgres psql -U minder -d minder -c "\dt"

echo "✅ Migration complete!"
```

---

## ✅ Step 3: Post-Migration Validation

```bash
#!/bin/bash
# Validate PostgreSQL 17 migration

echo "=== Post-Migration Validation ==="

# Check PostgreSQL version
echo "1. PostgreSQL Version:"
docker exec minder-postgres psql -U minder -c "SELECT version();"

# List all databases
echo ""
echo "2. Database List:"
docker exec minder-postgres psql -U minder -l

# Check tables in main database
echo ""
echo "3. Tables in minder database:"
docker exec minder-postgres psql -U minder -d minder -c "\dt"

# Test connectivity
echo ""
echo "4. Testing application connectivity..."
./setup.sh start

sleep 10

./setup.sh health

echo ""
echo "✅ Validation complete!"
```

---

## 🔄 Rollback Procedure

If migration fails:

```bash
#!/bin/bash
# Rollback to PostgreSQL 16

echo "=== Rolling Back to PostgreSQL 16 ==="

# Stop services
./setup.sh stop

# Restore docker-compose.yml
git checkout infrastructure/docker/docker-compose.yml

# Remove PostgreSQL 17 volume
docker volume rm docker_postgres_data

# Restore PostgreSQL 16 data
BACKUP_DIR="$1"  # Pass backup directory
docker run --rm \
  -v docker_postgres_data:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar xzf /backup/postgres_data.tar.gz -C /data

# Start services
./setup.sh start

echo "✅ Rollback complete!"
```

---

## 📊 Success Criteria

Migration is successful if:
- ✅ PostgreSQL 17 is running
- ✅ All 5 databases exist
- ✅ All tables are present
- ✅ Application can connect
- ✅ Health checks pass
- ✅ No data corruption

---

## 🆘 Troubleshooting

### Issue 1: Container won't start
```bash
docker logs minder-postgres
# Check for catalog version mismatch
```

### Issue 2: Data corruption
```bash
# Stop immediately
./setup.sh stop

# Verify backup integrity
grep "CREATE DATABASE" $BACKUP_DIR/full_backup.sql

# Perform rollback
./rollback_to_pg16.sh $BACKUP_DIR
```

### Issue 3: Connection errors
```bash
# Check network
docker network ls | grep minder

# Check port binding
docker ps | grep postgres

# Verify environment variables
docker exec minder-postgres env | grep POSTGRES
```

---

## 📞 Support

For issues or questions:
- GitHub Issues: https://github.com/wish-maker/minder/issues
- Documentation: See docs/operations/
- Backup Location: /tmp/postgres-migration-*

---

**Last Updated:** 2026-05-01  
**Migration Risk:** HIGH  
**Estimated Downtime:** 15-30 minutes  
**Rollback Capability:** FULL
