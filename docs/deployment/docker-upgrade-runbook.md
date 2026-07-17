# Minder Platform — Docker Image Upgrade Runbook

**Platform:** Raspberry Pi 4 (RPi-4-01, ARM64, 8 GB RAM)
**Environment:** Development (production hardening not yet applied)
**Last Updated:** 2026-07-10

---

## Overview

This runbook covers upgrading the Docker image versions used by the Minder platform, plus
the special handling required for a **PostgreSQL major-version** upgrade (which needs a
dump/restore rather than an in-place volume swap).

### How versions are managed (read this first)

- **`docker/compose/docker-compose.yml` is the hand-maintained single source of truth.**
  Image versions are pinned directly on the `image:` lines. You edit this file to change a
  version — there is **no template and no regeneration step** (the old
  template/regenerate machinery was removed in #31). Do **not** look for
  `.setup/templates/…` or a `compose_gen.sh`; they no longer exist.
- **`versions.sh`** *derives* the version list from the compose `image:` lines and produces
  a **drift report** (installed vs. pinned vs. latest available). It does not itself edit
  the compose file.
- **`bash setup.sh update`** performs the update flow (pull + recreate) for the pinned
  images.
- **CI (`.github/workflows/docker-image-update.yml`)** periodically checks upstream
  registries and **proposes** version bumps via PR. A human reviews and merges; the merged
  compose file is what ships. CI reads/edits the compose file directly — it never touches a
  template.

> Bottom line: to change an image version, edit the `image:` tag in
> `docker/compose/docker-compose.yml`, commit it, then apply with `bash setup.sh update`.

---

## Pre-Upgrade Checklist

- [ ] Confirm the Pi has enough free disk for a dump (databases can be several GB).
- [ ] All services healthy: `bash setup.sh status` and `bash setup.sh doctor`.
- [ ] Take a fresh backup: **`bash setup.sh backup`** (see
      `infrastructure-backup-strategy.md`).
- [ ] Review the proposed version changes (the CI PR diff, or `versions.sh` drift report).
- [ ] Note current versions so you can roll back.

```bash
# See installed vs. pinned vs. latest (drift report)
bash setup.sh update --check   # native-Python version engine (scripts/setup/versions.py)

# Snapshot current image tags for rollback reference
grep -nE '^\s*image:' docker/compose/docker-compose.yml
```

---

## Standard Image Upgrade (no data migration)

Most image bumps (Grafana, Prometheus, Traefik, Redis minor, exporters, etc.) are safe
in-place upgrades: the volume format is compatible, so pulling the new tag and recreating
the container is enough.

### Step 1 — Back up

```bash
bash setup.sh backup
```

### Step 2 — Update the pinned version

Edit the `image:` tag in `docker/compose/docker-compose.yml` (or merge the CI-proposed
PR). Example:

```yaml
# docker/compose/docker-compose.yml
services:
  grafana:
    image: grafana/grafana:13.1        # bump to the new pinned tag
```

### Step 3 — Apply

```bash
# Pull + recreate per the pinned compose
bash setup.sh update

# Or target a single service manually:
docker compose --file docker/compose/docker-compose.yml pull grafana
docker compose --file docker/compose/docker-compose.yml up -d grafana
```

### Step 4 — Verify

```bash
bash setup.sh status
docker ps --format "table {{.Names}}\t{{.Status}}"
```

Remember: `otel-collector`, `redis-exporter`, and `rabbitmq-exporter` have **no
healthcheck by design** — they will show "no healthcheck", which is normal, not
"unhealthy".

---

## PostgreSQL Major-Version Upgrade (Critical Path)

A **major** PostgreSQL version change (e.g. the data directory format changes) cannot be
done by simply swapping the image — the new server will refuse an old-format volume. Use a
logical dump/restore.

> The platform currently pins `postgres:18.4-trixie`. Only follow this section when you
> are actually crossing a major version that changes the on-disk format.

### Step 1 — Quiesce writers and dump

```bash
# Stop the app services that write to Postgres (leave DBs/monitoring up)
docker compose --file docker/compose/docker-compose.yml stop \
  api-gateway plugin-registry plugin-state-manager \
  marketplace rag-pipeline model-management tts-stt graph-rag openwebui

BACKUP_DIR="./backups/pg-upgrade-$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"

# pg_dumpall captures ALL databases + global objects (roles, grants).
# The main DB plus aux DBs: minder_marketplace, tefas_db, weather_db,
# news_db, crypto_db, minder_schemaregistry.
docker exec minder-postgres pg_dumpall -U "$POSTGRES_USER" > "$BACKUP_DIR/postgres_full_dump.sql"
sha256sum "$BACKUP_DIR/postgres_full_dump.sql" > "$BACKUP_DIR/postgres_dump.sha256"
ls -lh "$BACKUP_DIR"
```

### Step 2 — Replace the container and volume

```bash
# Verify the dump exists before destroying anything
[ -s "$BACKUP_DIR/postgres_full_dump.sql" ] || { echo "ABORT: empty/missing dump"; exit 1; }

docker compose --file docker/compose/docker-compose.yml stop postgres
docker compose --file docker/compose/docker-compose.yml rm -f postgres

# Remove the old data volume (name is <project>_postgres_data — confirm first)
docker volume ls | grep postgres_data
docker volume rm <project>_postgres_data
```

### Step 3 — Bump the pinned image and start fresh

Edit `docker/compose/docker-compose.yml` to the new `postgres:` tag, then:

```bash
docker compose --file docker/compose/docker-compose.yml up -d postgres

# Wait for readiness
until docker exec minder-postgres pg_isready -U "$POSTGRES_USER"; do sleep 5; done
```

### Step 4 — Restore

```bash
# pg_dumpall output recreates databases, roles and grants
docker exec -i minder-postgres psql -U "$POSTGRES_USER" < "$BACKUP_DIR/postgres_full_dump.sql"

# Sanity: list databases
docker exec minder-postgres psql -U "$POSTGRES_USER" -c "\l"
```

> If the app-side password in `./.env` and the restored role password diverge, run
> `bash setup.sh sync-postgres-password`.

### Step 5 — Migrate schema and bring services back

```bash
# Apply any pending schema migrations
bash setup.sh migrate

# Start everything
bash setup.sh start
bash setup.sh status
```

---

## Verification

```bash
# Core API health
curl -f http://localhost:8000/health   # api-gateway
curl -f http://localhost:8001/health   # plugin-registry

# Monitoring
curl -f http://localhost:9090/-/healthy # prometheus
curl -f http://localhost:3000/api/health # grafana

# Data stores (internal — exec into containers)
docker exec minder-postgres pg_isready -U "$POSTGRES_USER"
docker exec minder-redis redis-cli -a "$REDIS_PASSWORD" ping

# Overall
bash setup.sh doctor

# Resource usage on the Pi
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

---

## Rollback

### Revert an image bump

```bash
# Restore the previous pinned tag(s) in the compose file
git checkout -- docker/compose/docker-compose.yml   # if the bump was committed
# ...or hand-edit the image: tag back to the previous version

bash setup.sh update
```

### Roll back a failed Postgres major upgrade

```bash
docker compose --file docker/compose/docker-compose.yml stop postgres
docker compose --file docker/compose/docker-compose.yml rm -f postgres
docker volume rm <project>_postgres_data

# Revert the postgres: tag in the compose file to the previous major, then:
docker compose --file docker/compose/docker-compose.yml up -d postgres
until docker exec minder-postgres pg_isready -U "$POSTGRES_USER"; do sleep 5; done
docker exec -i minder-postgres psql -U "$POSTGRES_USER" < "$BACKUP_DIR/postgres_full_dump.sql"

bash setup.sh start
```

### Full restore

If a broader failure occurs, restore from the pre-upgrade backup:

```bash
bash setup.sh stop
bash setup.sh restore
bash setup.sh start
```

---

## Notes on ARM

- All pinned images must have an `arm64`/`linux/arm64` variant — the Pi 4 is ARM64. The CI
  update job and manual bumps should only propose tags that publish ARM builds.
- Memory is the constraint on a Pi 4 (8 GB). See `hardware-optimization.md`: the API
  gateway is capped at 2 G / 2 CPU in compose; Ollama and Neo4j are the next largest
  consumers. Verify RAM headroom (`free -h`) before and after an upgrade.

---

## Success Criteria

- [ ] All containers `healthy` (or "no healthcheck" for the 3 by-design exceptions); none
      stuck `restarting`.
- [ ] Core API and monitoring health checks pass.
- [ ] Postgres data intact (row counts match pre-upgrade for key tables).
- [ ] No error spikes in logs for ~30 minutes: `docker logs minder-<service> --tail 100 -f`.
- [ ] `bash setup.sh doctor` clean.

---

**Rollback:** Backup via `bash setup.sh backup`; restore via `bash setup.sh restore`.
**Backup location:** `./backups/…` and the MinIO `backup-archives` bucket.
