# PostgreSQL Migration Guide

**Last Updated:** 2026-07-10

This guide covers two related topics:
1. Running Minder's own **schema migrations** (day-to-day).
2. Performing a **major PostgreSQL version upgrade** (occasional, higher risk).

---

## Current State

- **PostgreSQL image:** `postgres:18.4-trixie`
- **Container:** `minder-postgres` (internal port 5432, not host-exposed)
- **Databases:**
  - `minder` — main application database
  - `minder_marketplace` — marketplace data
  - `tefas_db`, `weather_db`, `news_db`, `crypto_db` — per-domain databases
  - `minder_schemaregistry` — isolated database backing the Apicurio schema registry
- **Extensions:** None custom

---

## Part 1: Schema Migrations (routine)

Minder ships its schema migrations through `setup.sh`. This is the normal way to apply schema
changes and does **not** touch the PostgreSQL server version.

```bash
# Apply pending migrations
bash setup.sh migrate
```

Compose is always invoked with the explicit file path, e.g.:

```bash
docker compose --file docker/compose/docker-compose.yml <command>
```

Migrations run against the databases listed above. Initialization SQL lives under
`docker/services/postgres/` (the tracked `init.sql` is the canonical clean-install
initializer).

---

## Part 2: Major Version Upgrade (occasional)

> **CRITICAL:** A major PostgreSQL upgrade can cause data loss. PostgreSQL data directories
> are **not** compatible across major versions — you must dump and restore. Do not proceed
> without a verified backup and a rollback plan.

### Pre-Upgrade Checklist

- [ ] Full logical backup of all databases created and verified
- [ ] Application stopped
- [ ] Maintenance window scheduled
- [ ] Team notified of downtime
- [ ] Rollback procedure understood

### Step 1: Create a Comprehensive Backup

```bash
#!/bin/bash
set -euo pipefail

echo "=== PostgreSQL backup ==="

# Stop all services
bash setup.sh stop

# Or use the built-in backup command (multi-database aware)
# bash setup.sh backup

BACKUP_DIR="/tmp/postgres-migration-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Logical dump of ALL databases (roles + data)
docker exec minder-postgres pg_dumpall -U minder > "$BACKUP_DIR/full_backup.sql"

# Also snapshot the raw data volume as a fallback.
# NOTE: the volume is prefixed with the compose PROJECT name (the compose dir is
# docker/compose/ → project "compose" → volume "compose_postgres_data"). Confirm the
# exact name with `docker volume ls | grep postgres` before running these commands.
docker run --rm \
  -v compose_postgres_data:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar czf /backup/postgres_data.tar.gz -C /data .

if [ -s "$BACKUP_DIR/full_backup.sql" ] && [ -s "$BACKUP_DIR/postgres_data.tar.gz" ]; then
    echo "Backup OK: $BACKUP_DIR"
    ls -lh "$BACKUP_DIR"
else
    echo "Backup FAILED"; exit 1
fi
```

### Step 2: Upgrade Procedure

`docker/compose/docker-compose.yml` is the hand-maintained single source of truth — edit the
`postgres:` image tag directly in that file (there is no template/regenerate step).

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:?Usage: $0 <backup_directory>}"
[ -f "$BACKUP_DIR/full_backup.sql" ] || { echo "Backup not found"; exit 1; }

# 1. Update the postgres image tag in the compose file (edit by hand or with sed)
#    e.g. postgres:18.4-trixie -> postgres:<new-major>-<variant>
#    Edit: docker/compose/docker-compose.yml

# 2. Remove the old data volume (IRREVERSIBLE — you are relying on the dump)
docker volume rm compose_postgres_data

# 3. Start the new PostgreSQL
docker compose --file docker/compose/docker-compose.yml up -d postgres

# 4. Wait for readiness
sleep 30
docker exec minder-postgres psql -U minder -c "SELECT version();"

# 5. Restore from the logical dump
cat "$BACKUP_DIR/full_backup.sql" | docker exec -i minder-postgres psql -U minder

# 6. Sanity check
docker exec minder-postgres psql -U minder -l
docker exec minder-postgres psql -U minder -d minder -c "\dt"

echo "Upgrade complete."
```

### Step 3: Post-Upgrade Validation

```bash
#!/bin/bash
set -euo pipefail

echo "1. Version:"
docker exec minder-postgres psql -U minder -c "SELECT version();"

echo "2. Databases (expect minder, minder_marketplace, tefas_db, weather_db, news_db, crypto_db, minder_schemaregistry):"
docker exec minder-postgres psql -U minder -l

echo "3. Tables in main DB:"
docker exec minder-postgres psql -U minder -d minder -c "\dt"

echo "4. Re-apply schema migrations and start the platform:"
bash setup.sh migrate
bash setup.sh start
sleep 10
bash setup.sh status
```

---

## Rollback Procedure

If the upgrade fails:

```bash
#!/bin/bash
set -euo pipefail

BACKUP_DIR="${1:?Usage: $0 <backup_directory>}"

bash setup.sh stop

# Restore the compose file to the previous image tag
git checkout docker/compose/docker-compose.yml

# Remove the failed volume and restore the raw data snapshot
docker volume rm compose_postgres_data
docker run --rm \
  -v compose_postgres_data:/data \
  -v "$BACKUP_DIR:/backup" \
  alpine tar xzf /backup/postgres_data.tar.gz -C /data

bash setup.sh start
echo "Rollback complete."
```

---

## Success Criteria

- PostgreSQL starts on the target version
- All 7 databases exist (`minder`, `minder_marketplace`, `tefas_db`, `weather_db`,
  `news_db`, `crypto_db`, `minder_schemaregistry`)
- Tables present in each database
- `bash setup.sh migrate` completes cleanly
- Application connects and `bash setup.sh status` is healthy

---

## Troubleshooting

### Container won't start after an upgrade

```bash
docker logs minder-postgres
# A "database files are incompatible with server" / catalog-version error means the data
# directory is from a different major version — you must restore from the logical dump.
```

### Connection errors

```bash
docker network ls | grep minder
docker ps -a --filter name=minder-postgres
docker exec minder-postgres env | grep POSTGRES
```

---

## Support

- GitHub Issues: https://github.com/wish-maker/minder/issues
- Backups: `/tmp/postgres-migration-*` (or the location produced by `setup.sh backup`)

---

**Last Updated:** 2026-07-10
**Current version:** postgres:18.4-trixie
**Routine migrations:** `bash setup.sh migrate`
