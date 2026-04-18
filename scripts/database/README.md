# Minder Database Management Scripts

This directory contains scripts for managing Minder databases.

## Available Scripts

### 1. `01_init_databases.sh`
Initializes all databases and creates required tables.

**Usage:**
```bash
export POSTGRES_PASSWORD="your_password"
./01_init_databases.sh
```

**What it does:**
- Creates 5 databases: fundmind, minder_news, minder_weather, minder_crypto, minder_network
- Creates all required tables with proper indexes
- Verifies table creation
- Sets up permissions

**When to run:**
- First time setup
- After database server reset
- When adding new tables

---

### 2. `02_backup_databases.sh`
Backs up all databases with timestamp.

**Usage:**
```bash
export POSTGRES_PASSWORD="your_password"
export BACKUP_DIR="/path/to/backups"  # Optional, defaults to /var/backups/minder
./02_backup_databases.sh
```

**What it does:**
- Dumps all databases to SQL files
- Compresses backups with gzip
- Removes backups older than 7 days (configurable)
- Reports backup file sizes

**When to run:**
- Before schema changes
- Before major updates
- Regular scheduled backups (cron)

**Cron job example:**
```bash
# Daily backup at 2 AM
0 2 * * * cd /root/minder && ./scripts/database/02_backup_databases.sh
```

---

### 3. `03_restore_databases.sh`
Restores a database from a backup file.

**Usage:**
```bash
export POSTGRES_PASSWORD="your_password"
./03_restore_databases.sh /path/to/backup_file.sql.gz
```

**What it does:**
- Lists available backups if no argument provided
- Confirms before restore (destructive operation)
- Decompresses and restores database

**When to run:**
- After data corruption
- When rolling back changes
- When migrating to new server

**⚠️ WARNING**: This will DELETE all existing data in the target database!

---

### 4. `04_cleanup_old_data.sh`
Removes old data based on retention policies.

**Usage:**
```bash
export POSTGRES_PASSWORD="your_password"

# Optional: Customize retention policies
export RETENTION_NEWS=90      # Keep news for 90 days
export RETENTION_WEATHER=30   # Keep weather for 30 days
export RETENTION_CRYPTO=60    # Keep crypto for 60 days
export RETENTION_NETWORK=7    # Keep network for 7 days
export RETENTION_TEFAS=365    # Keep TEFAS for 1 year

./04_cleanup_old_data.sh
```

**What it does:**
- Deletes old records based on retention policies
- Runs VACUUM ANALYZE to reclaim disk space
- Reports number of records deleted

**When to run:**
- Regular maintenance (weekly/monthly)
- When disk space is low
- Before major data imports

**⚠️ WARNING**: This will DELETE old data permanently!

---

### 5. `05_verify_data.sh`
Verifies data collection is working correctly.

**Usage:**
```bash
export POSTGRES_PASSWORD="your_password"
./05_verify_data.sh
```

**What it does:**
- Checks all databases exist
- Checks all tables exist
- Counts records in each table
- Shows latest data timestamp
- Reports data freshness

**When to run:**
- After initial setup
- After data collection jobs
- When troubleshooting data issues
- Periodic health checks

---

## Environment Variables

All scripts require these environment variables:

```bash
POSTGRES_HOST=postgres          # Default: postgres
POSTGRES_PORT=5432              # Default: 5432
POSTGRES_USER=postgres          # Default: postgres
POSTGRES_PASSWORD=your_password # REQUIRED
```

Optional variables:

```bash
BACKUP_DIR=/path/to/backups     # For backup script
RETENTION_*=days                # For cleanup script
```

---

## Quick Start Guide

### First Time Setup

```bash
# 1. Set your database password
export POSTGRES_PASSWORD="your_secure_password"

# 2. Initialize databases
./01_init_databases.sh

# 3. Verify setup
./05_verify_data.sh

# 4. Start the application
docker-compose up -d

# 5. Wait for data collection (check logs)
docker-compose logs -f minder

# 6. Verify data collection worked
./05_verify_data.sh
```

### Daily Operations

```bash
# Backup databases (run daily via cron)
./02_backup_databases.sh

# Check data collection health
./05_verify_data.sh

# Clean up old data (run weekly)
./04_cleanup_old_data.sh
```

### Recovery Operations

```bash
# List available backups
ls -lh /var/backups/minder/

# Restore from backup
./03_restore_databases.sh /var/backups/minder/fundmind_20260418_020000.sql.gz
```

---

## Troubleshooting

### Script fails with "database does not exist"
**Solution**: Run `01_init_databases.sh` first

### Script fails with "permission denied"
**Solution**: Make scripts executable:
```bash
chmod +x scripts/database/*.sh
```

### Script fails with "connection refused"
**Solution**: Check database is running:
```bash
docker-compose ps postgres
```

### Data verification shows "No data"
**Solution**: Check data collection jobs are running:
```bash
docker-compose logs -f minder
```

### Backup files are too large
**Solution**: Clean up old data first:
```bash
./04_cleanup_old_data.sh
```

---

## Best Practices

1. **Regular Backups**: Set up cron job for daily backups
2. **Monitor Disk Space**: Run cleanup script regularly
3. **Test Restores**: Periodically test backup restoration
4. **Verify Data**: Run verification script after data collection
5. **Monitor Logs**: Check application logs for collection errors

---

## Script Versioning

All scripts are version 1.0.0 (stable, production-ready).

Version changes will be logged in CHANGELOG.md.
