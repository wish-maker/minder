# External / Infrastructure Services Guide

**Last Updated:** 2026-07-10

## Overview

This guide covers the **third-party and infrastructure services** that back the Minder
platform: storage engines, the LLM runtime, observability, exporters, and the reverse proxy.
It also explains how to point selected data services (Redis, PostgreSQL, Qdrant) at external
cloud providers instead of the local Docker containers, using environment variables and
without modifying code.

Minder defines **31 containers** (Authelia excluded/disabled). `setup.sh install` seeds
the **standard** bundle profile (core + inference + rag + chat); monitoring, graph-rag,
and voice are opt-in (`setup.sh bundle enable <name>`, or `install --profile full` for
all 31), and `start` honours the recorded bundle state. The single source of truth is the
hand-maintained `docker/compose/docker-compose.yml`.

---

## Service Inventory (as deployed)

All containers attach to the internal `minder-network`. "Host port" means the service
publishes that port on the host; blank means internal-only (reachable via container name, and
in some cases via a Traefik route).

### Inference

| Service | Container | Image | Ports | Notes |
|---------|-----------|-------|-------|-------|
| Ollama | `minder-ollama` | `ollama/ollama:0.31.2` | 11434 (internal) | Profile-gated `internal-ollama`; runs only when `OLLAMA_BASE_URL` is empty (local mode). Models auto-pulled via `OLLAMA_PULL_MODELS`, stored in the `/root/.ollama/models` volume |
| OpenWebUI | `minder-openwebui` | `ghcr.io/open-webui/open-webui:v0.10.2` | 8080 (internal) | LLM chat UI; reached via Traefik (`chat.minder.local`) |

### Storage

| Service | Container | Image | Ports | Notes |
|---------|-----------|-------|-------|-------|
| PostgreSQL | `minder-postgres` | `postgres:18.4-trixie` | 5432 (internal) | Main DB + aux: `minder_marketplace`, `tefas_db`, `weather_db`, `news_db`, `crypto_db`, `minder_schemaregistry` |
| Redis | `minder-redis` | `redis:8.8.0-alpine` | 6379 (internal) | Cache, rate-limit, sessions |
| Qdrant | `minder-qdrant` | `qdrant/qdrant:v1.18.2` | 6333 (internal) | Vector DB for RAG |
| Neo4j | `minder-neo4j` | `neo4j:2026.05.0-community` | 7687 / 7474 (internal) | Graph DB (marketplace + graph-rag); 7474 Traefik-routed (IP-whitelisted) |
| MinIO | `minder-minio` | `minio/minio:RELEASE.2025-09-07T16-13-09Z` | 9000 / 9001 (internal) | **Real running container.** Buckets: rag-documents, tts-artifacts, fine-tuning-datasets, model-checkpoints, plugin-packages, backup-archives. Console (9001) Traefik-routed |
| RabbitMQ | `minder-rabbitmq` | `rabbitmq:4.3.2-management` | 5672 / 15672 (internal) | Queue + mgmt UI; 15672 Traefik-routed (IP-whitelisted) |
| Schema Registry | `minder-schema-registry` | `apicurio/apicurio-registry-sql:2.6.13.Final` | 8080 (internal) | Backed by the isolated `minder_schemaregistry` PostgreSQL DB |

### Observability

| Service | Container | Image | Ports | Notes |
|---------|-----------|-------|-------|-------|
| Prometheus | `minder-prometheus` | `prom/prometheus:v3.13.0` | 9090 (host) | Metrics collection |
| Grafana | `minder-grafana` | `grafana/grafana:13.1` | 3000 (host) | Dashboards; Traefik-routed |
| Alertmanager | `minder-alertmanager` | `prom/alertmanager:v0.33.1` | 9093 (host) | Alert routing |
| InfluxDB | `minder-influxdb` | `influxdb:3.10.1-core` | 8086 (host) | Time-series |
| Telegraf | `minder-telegraf` | `telegraf:1.39.1` | — | Metrics agent |
| Jaeger | `minder-jaeger` | `jaegertracing/all-in-one:1.76.0` | 16686 (host, UI) + OTLP/thrift/zipkin | Distributed tracing |
| OTel Collector | `minder-otel-collector` | `otel/opentelemetry-collector:0.156.0` | 14317 (OTLP gRPC), 14318 (OTLP HTTP), 18888 (metrics) | No healthcheck by design |

### Exporters (internal, scraped by Prometheus)

| Service | Image | Port | Notes |
|---------|-------|------|-------|
| postgres-exporter | `v0.20.1` | 9187 | |
| redis-exporter | `v1.86.0` | 9121 | No healthcheck (by design) |
| rabbitmq-exporter | `v1.0.0-RC9` | 9090 | Healthcheck disabled |
| node-exporter | `v1.11.1` | 9100 | |
| cadvisor | `gcr.io/cadvisor/cadvisor:v0.55.1` | 8080 | Container metrics |
| blackbox-exporter | `v0.28.0` | 9115 | Endpoint probing |

### Security & Networking

| Service | Container | Image | Ports | Notes |
|---------|-----------|-------|-------|-------|
| Traefik | `minder-traefik` | `traefik:v3.7.7` | 80 / 443 / 8081 (host) | Reverse proxy, TLS, label-based routing (`exposedByDefault: false`). Dashboard (8081) IP-whitelisted |
| Authelia | `minder-authelia` | — | — | **DISABLED** — commented out in compose (crash loop / decision deferred). Traefik forward-auth is wired on a few routers but not enforced. Not counted in the 31 containers |

> **Healthchecks:** 28 of 31 containers have healthchecks. `otel-collector`, `redis-exporter`,
> and `rabbitmq-exporter` intentionally have none (image tooling limits) and appear as
> "no-healthcheck", not "unhealthy".

---

## Swappable Data Services (external providers)

The three stateful data services below can be pointed at external cloud endpoints via
environment variables. Everything else in the inventory above is expected to run locally.

### 1. Redis (Caching, Rate Limiting, Sessions)

**Providers:**
- AWS ElastiCache
- Redis Labs
- Redis Cloud
- Azure Cache for Redis
- Google Cloud Memorystore

**Configuration:**
```bash
# ./.env  (root — single source of truth; setup.sh mirrors it to docker/compose/.env)
REDIS_HOST=your-redis-cluster.example.com
REDIS_PORT=6379
REDIS_PASSWORD=your-secure-password
```

**Example: AWS ElastiCache**
```bash
REDIS_HOST=minder-redis.xxxxx.use1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_PASSWORD=your-elasticache-password
```

### 2. PostgreSQL (Primary Database)

**Providers:**
- AWS RDS
- Heroku Postgres
- Neon
- Supabase
- Google Cloud SQL
- Railway

**Configuration:**
```bash
# ./.env  (root — single source of truth; setup.sh mirrors it to docker/compose/.env)
POSTGRES_HOST=your-postgres-db.example.com
POSTGRES_PORT=5432
POSTGRES_USER=minder
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=minder
POSTGRES_SSLMODE=require
```

**Example: AWS RDS**
```bash
POSTGRES_HOST=minder-db.xxxxx.us-east-1.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_USER=minder
POSTGRES_PASSWORD=YourRdsPassword!123
```

**Example: Heroku Postgres**
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 3. Qdrant (Vector Database)

**Providers:**
- Qdrant Cloud
- Self-hosted Qdrant cluster

**Configuration:**
```bash
# ./.env  (root — single source of truth; setup.sh mirrors it to docker/compose/.env)
QDRANT_HOST=your-cluster.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=your-qdrant-cloud-api-key
QDRANT_TLS=true
```

**Example: Qdrant Cloud**
```bash
QDRANT_HOST=https://your-cluster.qdrant.io
QDRANT_API_KEY=xyz-your-api-key
```

---

## Usage Scenarios

### Scenario 1: Local Development (Default)

All services run in local Docker containers.

```bash
bash setup.sh start
# (setup.sh invokes: docker compose --file docker/compose/docker-compose.yml up -d)
```

**Services (internal-only — reachable by container name on `minder-network`, not published on the host):**
- PostgreSQL: `minder-postgres:5432`
- Redis: `minder-redis:6379`
- Qdrant: `minder-qdrant:6333`

### Scenario 2: Hybrid (Local + External)

Some services local, some external.

**Example: Local Redis + Cloud PostgreSQL**
```bash
# ./.env  (root — single source of truth; setup.sh mirrors it to docker/compose/.env)
POSTGRES_HOST=aws-rds.amazonaws.com
POSTGRES_PASSWORD=production-password

REDIS_HOST=localhost
REDIS_PORT=6379
```

```bash
docker compose --file docker/compose/docker-compose.yml up -d redis  # local Redis; PostgreSQL is external
```

### Scenario 3: Full External (Production)

All services external, no local databases.

```bash
# ./.env  (root — single source of truth; setup.sh mirrors it to docker/compose/.env)
REDIS_HOST=redis-cloud.example.com
POSTGRES_HOST=rds.amazonaws.com
QDRANT_HOST=qdrant-cloud.io
```

```bash
docker compose --file docker/compose/docker-compose.yml up -d api-gateway plugin-registry  # microservices only
```

### Scenario 4: Per-Machine Configuration

Minder uses **one root `./.env` per machine** (no `--env-file` layering). Each
deployment keeps its own endpoints in its own `./.env`:

**On a development machine — `./.env`**
```bash
POSTGRES_HOST=localhost
REDIS_HOST=localhost
QDRANT_HOST=localhost
```

**On a production machine — `./.env`**
```bash
POSTGRES_HOST=prod-rds.amazonaws.com
REDIS_HOST=prod-redis.xxxxx.use1.cache.amazonaws.com
QDRANT_HOST=https://prod-qdrant.qdrant.io
```

Then on each machine simply:
```bash
bash setup.sh start   # reads ./.env, mirrors it to docker/compose/.env, starts
```

---

## Service-Specific Configuration

### API Gateway Configuration

The API Gateway reads connection settings from environment variables:

```python
# src/services/api-gateway/config.py
class Settings:
    REDIS_HOST: str = "minder-redis"           # Default: local container
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "dev_password_change_me"

    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"
```

### Plugin Registry Configuration

```python
# src/services/plugin-registry/config.py
class Settings:
    POSTGRES_HOST: str = "minder-postgres"       # Default: local container
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "minder"
    POSTGRES_PASSWORD: str = "dev_password_change_me"
    POSTGRES_DB: str = "minder"
```

### RAG Pipeline Configuration

```python
# src/services/rag-pipeline/ config
class Settings:
    QDRANT_HOST: str = "minder-qdrant"         # Default: local container
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""  # For Qdrant Cloud
```

---

## Migration Guide

### From Local to External Redis

1. **Create external Redis** (e.g., AWS ElastiCache)
2. **Update .env file:**
   ```bash
   REDIS_HOST=your-elasticache-endpoint.use1.cache.amazonaws.com
   REDIS_PASSWORD=your-elasticache-password
   ```
3. **Restart services:**
   ```bash
   docker compose restart api-gateway plugin-registry
   ```
4. **Verify connection:**
   ```bash
   docker logs minder-api-gateway | grep -i redis
   ```

### From Local to External PostgreSQL

1. **Create external PostgreSQL** (e.g., AWS RDS)
2. **Run init script on external database:**
   ```bash
   psql -h your-rds.amazonaws.com -U minder -d postgres < docker/services/postgres/init.sql
   ```
3. **Update .env file:**
   ```bash
   POSTGRES_HOST=your-rds.amazonaws.com
   POSTGRES_PASSWORD=your-rds-password
   ```
4. **Restart services:**
   ```bash
   docker compose restart plugin-registry
   ```

### From Local to External Qdrant

1. **Create Qdrant Cloud account**
2. **Get cluster URL and API key**
3. **Update .env file:**
   ```bash
   QDRANT_HOST=your-cluster.qdrant.io
   QDRANT_API_KEY=your-api-key
   ```
4. **Restart RAG Pipeline:**
   ```bash
   docker compose --file docker/compose/docker-compose.yml restart rag-pipeline
   ```

---

## Troubleshooting

### Connection Refused Errors

**Problem:** `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solution:**
1. Check external service is reachable: `telnet your-redis-host 6379`
2. Verify security group allows access from your IP
3. Check password is correct

### SSL/TLS Errors

**Problem:** `ssl.SSLError: [SSL: WRONG_VERSION_NUMBER]`

**Solution:**
```bash
# Add TLS configuration
REDIS_TLS=true
POSTGRES_SSLMODE=require
```

### DNS Resolution Errors

**Problem:** `Name or service not known`

**Solution:**
1. Verify host is correct
2. Check DNS settings
3. Try using IP address directly

### Plugin Loading Failures

**Problem:** Plugins fail to load with database errors

**Solution:**
1. Verify external PostgreSQL is accessible: `docker exec minder-plugin-registry ping -c 3 your-postgres-host`
2. Check database exists: `psql -h your-host -U minder -l | grep minder`
3. Run init script if needed

---

## Best Practices

### Security
- Never commit `.env` files with real passwords to git
- Use different passwords for dev/staging/production
- Rotate credentials regularly
- Use IAM authentication where possible (AWS RDS)

### High Availability
- Use Redis Cluster for production
- Use PostgreSQL Multi-AZ deployments
- Enable connection pooling
- Configure retry logic in applications

### Performance
- Use same region for all services (reduce latency)
- Enable Redis persistence
- Configure PostgreSQL connection pooling
- Use Qdrant replication for production

### Monitoring
- Set up health checks for external services
- Configure alerts for connection failures
- Monitor resource usage (CPU, memory, connections)
- Log connection errors for troubleshooting

---

## Quick Reference

| Service | Environment Variable | Default Value | Example External |
|---------|---------------------|---------------|------------------|
| Redis | REDIS_HOST | minder-redis | redis-12345.c1.us-east-1-2.aws.cloud.redislabs.com |
| PostgreSQL | POSTGRES_HOST | minder-postgres | minder-db.xxxxx.us-east-1.rds.amazonaws.com |
| Qdrant | QDRANT_HOST | minder-qdrant | your-cluster.qdrant.io |

---

## Support

For issues or questions:
1. Check service logs: `docker logs <container-name>`
2. Test connectivity: `telnet <host> <port>`
3. Review this guide's troubleshooting section
4. Check service provider documentation

---

*Last Updated: 2026-07-10 · 31 containers · Development environment*
