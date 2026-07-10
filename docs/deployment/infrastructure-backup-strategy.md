# Minder Platform Backup & Restore

**Version:** 2.0.0
**Last Updated:** 2026-07-10
**Status:** 🟢 Built into `setup.sh`

> Deployment target is a Raspberry Pi 4 (RPi-4-01, ARM). This is a **development
> environment**; production hardening is not yet applied. State lives in Docker named
> volumes and MinIO buckets; there is no separate database host.

---

## 📦 Backup & Restore via `setup.sh`

Minder ships backup and restore as first-class `setup.sh` verbs. Prefer these over
hand-rolled scripts — they know the exact volume names, container names, and MinIO
buckets.

```bash
# Create a backup
bash setup.sh backup

# Restore from a backup
bash setup.sh restore
```

The full `setup.sh` command set:

```
install | start | stop | restart | status | logs | shell | migrate |
backup | restore | doctor | update | ollama-mode |
sync-postgres-password | uninstall
```

Compose is always invoked as
`docker compose --file docker/compose/docker-compose.yml ...`.

---

## 🗄️ What Needs Backing Up

### Docker named volumes (persistent state)

All persistent data lives in Docker **named volumes** (not host bind-mounts). The volumes
that hold real state include:

| Volume | Backs | Notes |
|---|---|---|
| `postgres_data` | PostgreSQL (`postgres:18.4-trixie`) | Users, sessions, metadata + aux DBs (marketplace, tefas/weather/news/crypto, schema-registry) |
| `redis_data` | Redis (`redis:8.8.0-alpine`) | Cache, rate-limit state, sessions |
| `neo4j_data` | Neo4j (`neo4j:2026.05.0-community`) | Graph relationships (marketplace + graph-rag) |
| `qdrant_data` | Qdrant (`qdrant/qdrant:v1.18.2`) | Vector embeddings for RAG |
| `minio_data` | MinIO object store | See buckets below |
| `rabbitmq_data` | RabbitMQ (`rabbitmq:4.3.2-management`) | Queues, pipeline triggers |
| `influxdb_data` | InfluxDB (`influxdb:3.10.1-core`) | Time-series metrics |
| `ollama_data` | Ollama model storage | Pulled models under `/root/.ollama/models` |

> Volume names are prefixed by the Compose project at runtime (e.g.
> `<project>_postgres_data`). Confirm exact names with `docker volume ls`.

### MinIO buckets

MinIO (`minder-minio`) is a real running container. Its buckets:

- `rag-documents`
- `tts-artifacts`
- `fine-tuning-datasets`
- `model-checkpoints`
- `plugin-packages`
- `backup-archives` ← backup artifacts land here

### Configuration

- `./.env` — the **single source of truth** for configuration/secrets. `setup.sh`
  auto-heals it and mirrors it to `docker/compose/.env` (auto-generated — do **not** back
  up or edit the mirror; back up the root file).
- `docker/compose/docker-compose.yml` — hand-maintained source of truth for the stack.
- `docker/services/traefik/` — reverse-proxy dynamic config.

---

## 🔁 Restore

```bash
bash setup.sh restore
```

For a full recovery:

1. Stop services: `bash setup.sh stop`
2. Restore the relevant Docker volumes / MinIO buckets from the backup archive.
3. Ensure `./.env` is present and correct.
4. Start services: `bash setup.sh start`
5. Verify: `bash setup.sh status` and `bash setup.sh doctor`

> If the PostgreSQL password in `./.env` was rotated relative to the volume's stored
> password, use `bash setup.sh sync-postgres-password` to reconcile them.

---

## 🧰 Manual Backups (fallback / reference)

If you need to script backups outside `setup.sh` (e.g. an external cron on the Pi), the
building blocks are below. These are illustrative fallbacks — the built-in
`setup.sh backup` is the supported path.

### PostgreSQL

```bash
docker exec minder-postgres pg_dump -U "$POSTGRES_USER" -d minder | gzip > minder-postgres-$(date +%Y%m%d).sql.gz
```

### Neo4j

```bash
docker exec minder-neo4j neo4j-admin database dump neo4j --to-path=/backups
docker cp minder-neo4j:/backups ./neo4j-backup-$(date +%Y%m%d)
```

### Docker volume snapshot

```bash
# Discover exact names first
docker volume ls | grep -E 'postgres_data|neo4j_data|qdrant_data|redis_data|rabbitmq_data|minio_data|ollama_data|influxdb_data'

# Snapshot one volume (replace <project> with the compose project prefix)
docker run --rm \
  -v <project>_postgres_data:/data \
  -v "$(pwd)":/backup \
  alpine tar -czf /backup/postgres_data-$(date +%Y%m%d).tar.gz -C /data .
```

### Configuration

```bash
tar -czf minder-config-$(date +%Y%m%d).tar.gz \
  .env \
  docker/compose/docker-compose.yml \
  docker/services/traefik
```

---

## 📅 Suggested Schedule

| Cadence | Scope |
|---|---|
| Daily | `bash setup.sh backup` (databases + volumes) |
| Weekly | Configuration (`./.env`, compose, Traefik config) |
| Before any change | Ad-hoc `bash setup.sh backup` |

Retention and off-Pi copies (e.g. `rsync` to another host) are left to the operator —
the Pi's local storage is limited, so pruning old archives and shipping them off-device is
recommended.

---

## 🔍 Verification

```bash
# List backup artifacts (MinIO backup-archives bucket, or local dir)
# Restore into a throwaway/staging environment and diff, then:
bash setup.sh status
bash setup.sh doctor
```

Test a real restore periodically — an untested backup is not a backup.

---

## 🚧 Not Yet Built (future work)

The following were once aspirational and are **not implemented** today; treat as forward
work, not current behavior:

- Prometheus `backup_success_total` / `backup_size_bytes` metrics and Alertmanager rules
  for backup health.
- A dedicated Grafana backup dashboard.
- Automated retry/notification on backup failure.

---

**Status:** 🟢 `setup.sh backup` / `restore` available. Metrics, alerting, and off-site
retention are future enhancements.
