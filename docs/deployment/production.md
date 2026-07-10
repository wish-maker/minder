# Deployment Guide

**Version:** 2.0
**Target:** Raspberry Pi 4 (RPi-4-01, ARM64)
**Status:** Development environment — production hardening not yet applied
**Last Updated:** 2026-07-10

---

## Overview

Minder is a full-stack AI orchestration platform that runs entirely in Docker on a single
**Raspberry Pi 4 (ARM64)**. It is currently a **development deployment**: it is functional
end-to-end, but production hardening (real TLS certs, enforced SSO, secret rotation, HA,
etc.) has **not** been applied. Treat the "production" material in this guide as a
forward-looking checklist, not a description of current state.

Everything is provisioned by a single script and a single hand-maintained compose file:

- **Compose:** `docker/compose/docker-compose.yml` — the hand-maintained **single source
  of truth**. There is no template and no regeneration step (that machinery was removed).
  Edit this file directly to change the stack.
- **Config/secrets:** root **`./.env`** is the single source of truth. `setup.sh`
  auto-heals it and mirrors it to `docker/compose/.env` (auto-generated — do not edit the
  mirror). There is no file-secrets overlay and no multi-environment machinery.
- **Provisioning:** `bash setup.sh` (see command list below).

---

## `setup.sh` Commands

```
install | start | stop | restart | status | logs | shell | migrate |
backup | restore | doctor | update | ollama-mode |
sync-postgres-password | uninstall
```

Compose is always invoked as
`docker compose --file docker/compose/docker-compose.yml ...`.

| Command | Purpose |
|---|---|
| `install` | First-time setup (env heal, images, volumes, migrate) |
| `start` / `stop` / `restart` | Lifecycle for the whole stack |
| `status` | Container/health overview |
| `logs` | Stream service logs |
| `shell` | Open a shell in a service container |
| `migrate` | Apply database schema migrations |
| `backup` / `restore` | Backup and restore (see `infrastructure-backup-strategy.md`) |
| `doctor` | Diagnostics / health checks |
| `update` | Pull + recreate pinned images (see `docker-upgrade-runbook.md`) |
| `ollama-mode` | Switch between local-container and external/native Ollama |
| `sync-postgres-password` | Reconcile `./.env` Postgres password with the volume |
| `uninstall` | Tear down |

---

## Quick Deploy

```bash
# Clone
git clone git@github.com:wish-maker/minder.git
cd minder

# Configure: root ./.env is the single source of truth.
# setup.sh auto-fills any CHANGEME secrets you leave and mirrors ./.env to
# docker/compose/.env — you do not copy it by hand.
cp .env.example .env      # if a template is provided; otherwise setup.sh creates it
$EDITOR .env              # set any values you want to control explicitly

# Install (heals env, pulls images, creates volumes, runs migrations, starts stack)
bash setup.sh install

# Verify
bash setup.sh status
bash setup.sh doctor
```

To start/stop later:

```bash
bash setup.sh start
bash setup.sh stop
```

---

## Service Map

31 containers run on the Pi (Authelia is defined but currently **disabled** and not
counted). Only Traefik and the app/monitoring services below expose host ports; all
storage backends are **internal-only** and reached over the Docker network or via Traefik.

### Core API services (8 — all FastAPI)

| Service | Container | Host Port |
|---|---|---|
| API Gateway | `minder-api-gateway` | 8000 |
| Plugin Registry | `minder-plugin-registry` | 8001 |
| Marketplace | `minder-marketplace` | 8002 |
| Plugin State Manager | `minder-plugin-state-manager` | 8003 |
| RAG Pipeline | `minder-rag-pipeline` | 8004 |
| Model Management | `minder-model-management` | 8005 |
| TTS / STT | `minder-tts-stt` | 8006 |
| Graph-RAG | `minder-graph-rag` | 8008 |

> There is **no** `model-fine-tuning` service and **no** `ai-service` — both were
> intentionally removed. Do not add them back.

### Inference

- `minder-ollama` — `ollama/ollama:0.31.2`, internal 11434 (not host-exposed). Profile
  `internal-ollama`: runs only when `OLLAMA_BASE_URL` is empty (local mode). If
  `OLLAMA_BASE_URL` is set, inference is offloaded to an external/native host and the
  container is inactive. Switch with `bash setup.sh ollama-mode`.
- `minder-openwebui` — `ghcr.io/open-webui/open-webui:v0.10.2`, internal 8080, reached via
  Traefik. **This is the web UI** — there is no separate Next.js/React frontend.

### Storage (internal-only)

| Service | Container | Image |
|---|---|---|
| PostgreSQL | `minder-postgres` | `postgres:18.4-trixie` |
| Redis | `minder-redis` | `redis:8.8.0-alpine` |
| Qdrant (vectors) | `minder-qdrant` | `qdrant/qdrant:v1.18.2` |
| Neo4j (graph) | `minder-neo4j` | `neo4j:2026.05.0-community` |
| MinIO (objects) | `minder-minio` | `minio/minio:RELEASE.2025-09-07T16-13-09Z` |
| RabbitMQ | `minder-rabbitmq` | `rabbitmq:4.3.2-management` |
| Schema Registry | `minder-schema-registry` | `apicurio/apicurio-registry-sql:2.6.13.Final` |

### Observability

Prometheus (`:9090`), Grafana (`:3000`), Alertmanager (`:9093`), Jaeger (`:16686`),
OTel Collector (`:14317/14318/18888`), InfluxDB (`:8086`), Telegraf, plus six exporters.
See `monitoring.md` for the full stack and instrumentation details.

### Reverse proxy & auth

- **Traefik** (`traefik:v3.7.7`) — the reverse proxy, TLS termination, and router. Routing
  is via Docker labels (`exposedByDefault: false`). Host ports 80/443 and 8081 (dashboard,
  IP-whitelisted). **Minder does not use Nginx.**
- **Authelia** — **disabled** (commented out in compose) due to a crash loop; the
  keep-vs-drop decision is deferred. Traefik has an `authelia-forwardauth` middleware wired
  on five routers (minio, api-gateway, grafana, openwebui, jaeger), but because the container
  is down, that auth is **not enforced** today.

---

## Environment Configuration

```bash
# ./.env is the ONLY file you edit. setup.sh mirrors it to docker/compose/.env.
# Any value left as CHANGEME is auto-filled with a secure random value on start/install.

ENVIRONMENT=development      # this is a dev deployment
LOG_LEVEL=INFO

# Secrets (leave as CHANGEME to auto-generate, or set explicitly)
POSTGRES_PASSWORD=CHANGEME
REDIS_PASSWORD=CHANGEME
JWT_SECRET=CHANGEME
INFLUXDB_TOKEN=CHANGEME

# Ollama: empty => run locally in the container; set a URL => offload to that host
OLLAMA_BASE_URL=
OLLAMA_MODELS=llama3.2,nomic-embed-text
```

---

## Health Checks

```bash
# Overview
bash setup.sh status

# Core API
curl http://localhost:8000/health   # api-gateway
curl http://localhost:8001/health   # plugin-registry
curl http://localhost:8002/health   # marketplace
curl http://localhost:8003/health   # plugin-state-manager
curl http://localhost:8004/health   # rag-pipeline
curl http://localhost:8005/health   # model-management
curl http://localhost:8006/health   # tts-stt
curl http://localhost:8008/health   # graph-rag

# Monitoring
curl http://localhost:9090/-/healthy   # prometheus
curl http://localhost:3000/api/health  # grafana

# Ollama model list (internal port; exec into the container)
docker exec minder-ollama ollama list
```

28 of 31 containers define a Docker healthcheck. Three do **not**, by design
(`otel-collector`, `redis-exporter`, `rabbitmq-exporter`) — their base images lack the
tooling. They show as "no healthcheck", which is **not** the same as "unhealthy".

---

## Reverse Proxy (Traefik v3)

Traefik is already configured in `docker/compose/docker-compose.yml` and discovers services
automatically via Docker labels:

- Automatic service discovery (no manual upstream config)
- Load balancing across container replicas
- TLS termination
- Middleware pipeline (forward-auth, IP whitelist, headers)

Dashboard: `http://localhost:8081` (IP-whitelisted).

TLS today uses self-signed/local certs. For a real deployment, wire Traefik to Let's
Encrypt (ACME) or provide your own certificates. **Nginx/HAProxy are not used** — ignore
any older instructions to configure them.

---

## Resource Limits

Set limits directly in `docker/compose/docker-compose.yml`. The API gateway is the only
service with an active limit today:

```yaml
services:
  api-gateway:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2'
        reservations:
          memory: 512M
          cpus: '0.5'
```

On a single 8 GB Pi, size any additional limits conservatively — Ollama and Neo4j are the
largest RAM consumers. See `hardware-optimization.md`.

All services use `restart: unless-stopped`.

---

## Backups

Use the built-in commands (details in `infrastructure-backup-strategy.md`):

```bash
bash setup.sh backup
bash setup.sh restore
```

Persistent state lives in Docker named volumes (`postgres_data`, `neo4j_data`,
`qdrant_data`, `redis_data`, `rabbitmq_data`, `minio_data`, `ollama_data`, `influxdb_data`,
…) and in MinIO buckets (including `backup-archives`).

---

## Upgrades

Image versions are pinned in `docker/compose/docker-compose.yml` (hand-maintained).
`versions.sh` derives the list from the `image:` lines and reports drift; CI
(`docker-image-update.yml`) proposes bumps via PR. Apply with `bash setup.sh update`. Full
procedure — including PostgreSQL major-version migration — is in
`docker-upgrade-runbook.md`.

---

## Scaling

Traefik load-balances across replicas of a scaled stateless service:

```bash
docker compose --file docker/compose/docker-compose.yml up -d --scale api-gateway=2
```

> Note: Ollama is **not** scaled with `--scale` — it is profile-gated. Scaling only makes
> sense for stateless services. On a single Pi, headroom for horizontal scaling is limited.

---

## Troubleshooting

```bash
# Status / health
bash setup.sh status
docker compose --file docker/compose/docker-compose.yml ps

# Logs
docker logs minder-<service> --tail 100 -f

# Restart / recreate a service
docker compose --file docker/compose/docker-compose.yml restart <service>
docker compose --file docker/compose/docker-compose.yml up -d --force-recreate <service>

# Resource usage
docker stats --no-stream

# Diagnostics
bash setup.sh doctor
```

### Common issues

- **Service won't start** — check `docker logs <service>`; confirm `./.env` is populated
  (setup.sh mirrors it to `docker/compose/.env`); check dependency health.
- **High memory / OOM** — the Pi has 8 GB. Reduce Ollama model size or offload Ollama
  (`bash setup.sh ollama-mode`); see `hardware-optimization.md`.
- **DB connection issues** — `docker exec minder-postgres pg_isready -U "$POSTGRES_USER"`;
  if passwords diverged, run `bash setup.sh sync-postgres-password`.
- **Auth not enforced** — expected: Authelia is currently disabled.

---

## Production Hardening Checklist (future work)

The items below are **not** done yet. They are the gap between this development deployment
and a hardened one:

- [ ] Decide on and (re-)enable Authelia SSO/MFA, or remove it (decision deferred).
- [ ] Replace self-signed certs with real TLS (Let's Encrypt via Traefik or provided
      certs).
- [ ] Configure real DNS for the public hostnames.
- [ ] Firewall rules; restrict which ports are reachable externally.
- [ ] Secret rotation. (Optional: layer an external secrets manager on top of the `./.env`
      mechanism — not built in.)
- [ ] Configure Alertmanager receivers (email/Slack/PagerDuty) — currently placeholders.
- [ ] Establish and test a real backup retention + off-device copy policy.
- [ ] Review resource limits for expected load.

### Explicitly NOT implemented (do not assume these exist)

- **RBAC** — only JWT + bcrypt authentication exists in the API gateway; role-based access
  control is not implemented.
- **High availability / multi-server / multi-region** — this is a single-Pi deployment.
  Any HA or cloud-native (Kubernetes) topology is aspirational, not current.
- **Centralized logging (ELK/Loki)** — logs are per-container Docker logs.
- **Payment gateway, Kafka, Istio, Elasticsearch** — none of these are part of Minder.
- **Published performance benchmarks** — none are quoted here because none have been
  measured on this hardware. Measure with the monitoring stack before making SLO claims.

---

## Related Documentation

- [Monitoring Setup](monitoring.md)
- [Hardware Optimization](hardware-optimization.md)
- [Backup & Restore](infrastructure-backup-strategy.md)
- [Docker Upgrade Runbook](docker-upgrade-runbook.md)

---

**Last Updated:** 2026-07-10
