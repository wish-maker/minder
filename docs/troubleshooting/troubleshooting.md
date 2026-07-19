# Troubleshooting Guide - Minder Platform

**Last Updated:** 2026-07-10
**Platform Version:** 1.0.0
**Scale:** 31 containers (development environment on Raspberry Pi 4)

---

## Table of Contents

1. [First Steps](#first-steps)
2. [Service Health](#service-health)
3. [Healthchecks: What "no-healthcheck" Means](#healthchecks-what-no-healthcheck-means)
4. [App Services & Ports](#app-services--ports)
5. [Reverse Proxy (Traefik)](#reverse-proxy-traefik)
6. [Network Connectivity](#network-connectivity)
7. [Storage Backends](#storage-backends)
8. [Performance Issues](#performance-issues)
9. [Monitoring & Debugging](#monitoring--debugging)
10. [Emergency Procedures](#emergency-procedures)

---

## First Steps

The standard debugging order is: **logs → inspect → restart → network → resources.**

```bash
# Overview of everything
docker ps
bash setup.sh status

# Diagnostics
bash setup.sh doctor

# Tail a service's logs
docker logs minder-<service> --tail 50 -f
```

All services run as Docker containers named `minder-<service>`. Compose is at
`docker/compose/docker-compose.yml`; the root `./.env` is the single source of truth for
configuration.

---

## Service Health

### Check status

```bash
# All services
bash setup.sh status
docker ps

# Specific service
docker ps | grep api-gateway
docker logs minder-api-gateway --tail 50
```

### Restart a service

```bash
# Via setup.sh
bash setup.sh restart api-gateway

# Or directly
cd docker/compose && docker compose restart api-gateway
```

### Container in a restart loop

```bash
docker logs minder-<service> --tail 100

# Common causes: config error, missing env var, dependency not ready.
# Recreate after fixing:
cd docker/compose
docker compose up -d --force-recreate <service>
```

---

## Healthchecks: What "no-healthcheck" Means

28 of the 31 containers have Docker healthchecks. **Three do not, by design** — their base
images lack the tooling (e.g. `nc`) to run one:

- `minder-otel-collector`
- `minder-redis-exporter`
- `minder-rabbitmq-exporter`

These show as **`no-healthcheck`** (or blank health) in `docker ps`. **This is not a
failure.** Older docs that called `redis-exporter` or `otel-collector` "unhealthy" were
stale — they simply have no healthcheck defined. Verify they are actually working by
checking their logs or the metrics they emit, not by their (absent) health status.

```bash
# These are fine even with no health status:
docker logs minder-otel-collector --tail 30
docker logs minder-redis-exporter --tail 30
docker logs minder-rabbitmq-exporter --tail 30
```

---

## App Services & Ports

The eight core API services are host-exposed and each serves a `/health` endpoint:

| Service | Container | Health check |
|---------|-----------|--------------|
| api-gateway | minder-api-gateway | `curl http://localhost:8000/health` |
| plugin-registry | minder-plugin-registry | `curl http://localhost:8001/health` |
| marketplace | minder-marketplace | `curl http://localhost:8002/health` |
| plugin-state-manager | minder-plugin-state-manager | `curl http://localhost:8003/health` |
| rag-pipeline | minder-rag-pipeline | `curl http://localhost:8004/health` |
| model-management | minder-model-management | `curl http://localhost:8005/health` |
| tts-stt | minder-tts-stt | `curl http://localhost:8006/health` |
| graph-rag | minder-graph-rag | `curl http://localhost:8008/health` |

Other host-exposed endpoints: Prometheus `:9090`, Grafana `:3000`, Alertmanager `:9093`,
InfluxDB `:8086`, Jaeger UI `:16686`, Traefik `:80/:443` (dashboard `:8081`, IP-whitelisted).

Ollama (`:11434`) runs internally and is reached via other services, not a host port. The
web UI is **OpenWebUI**, reached through Traefik.

> Note: there is no `model-fine-tuning` service and no `ai-service` — those were removed.
> Do not look for a `:8007` service.

---

## Reverse Proxy (Traefik)

Minder uses **Traefik v3** as its reverse proxy (not Nginx). Routing is driven by Docker
labels; `exposedByDefault` is `false`, so only labeled services are routed.

### Symptom: 404 on a routed hostname

```bash
# Traefik logs
docker logs minder-traefik --tail 50

# Traefik-related env
grep TRAEFIK .env

# Restart Traefik
cd docker/compose && docker compose restart traefik
```

Several Traefik routers are wired with an Authelia forward-auth middleware, but **Authelia
is currently disabled** (commented out in compose). With Authelia down, that forward-auth
is **not enforced** — its keep/drop is an open decision. If you were expecting an auth
redirect and don't see one, this is why.

---

## Network Connectivity

Services share the `minder-network` Docker network and address each other by container
name (`minder-<service>`).

```bash
# List networks
docker network ls | grep minder

# Inspect
docker network inspect minder-network

# Service-to-service reachability (from inside a container)
docker exec minder-api-gateway curl -s http://minder-rag-pipeline:8004/health
docker exec minder-rag-pipeline curl -s http://minder-qdrant:6333/collections
```

### DNS resolution

```bash
docker exec minder-api-gateway getent hosts minder-postgres
docker exec minder-api-gateway getent hosts minder-redis
```

---

## Storage Backends

Storage services are **internal-only** (not exposed on host ports). Reach them by exec'ing
into their container (or, where routed, via Traefik).

### PostgreSQL

```bash
docker exec minder-postgres psql -U minder -c "SELECT version();"
docker exec minder-postgres psql -U minder -c "\l"     # list databases
docker exec minder-postgres pg_isready -U minder
```

### Redis

```bash
docker exec minder-redis redis-cli -a "$REDIS_PASSWORD" ping   # -> PONG
docker exec minder-redis redis-cli -a "$REDIS_PASSWORD" INFO memory
```

If AUTH fails, verify the password in the root `./.env`:

```bash
grep REDIS_PASSWORD .env
```

### Neo4j (graph DB — used by marketplace + graph-rag)

```bash
docker logs minder-neo4j --tail 50 | grep -i "started\|remote interface"
docker exec minder-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;"
```

### Qdrant (vector DB — used by rag-pipeline)

```bash
docker exec minder-qdrant sh -c "wget -qO- http://localhost:6333/collections"
```

### MinIO / RabbitMQ

```bash
docker logs minder-minio --tail 30
docker exec minder-rabbitmq rabbitmq-diagnostics status
```

MinIO (routed to `:9001` via Traefik) and RabbitMQ management (`:15672` via Traefik) are
reachable through the proxy where configured.

---

## Performance Issues

### Memory / CPU

```bash
docker stats --no-stream

# Restart a heavy service
bash setup.sh restart rag-pipeline

# Look for OOM signals
docker logs minder-<service> | grep -i "memory\|oom\|out of"
```

This is a Raspberry Pi 4 (ARM) — resources are limited. The AI services (rag-pipeline,
model-management) and Ollama inference are the usual pressure points.

### Slow responses

```bash
# Time a health endpoint
time curl -s http://localhost:8000/health

# Check DB connection saturation
docker exec minder-postgres psql -U minder -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

---

## Monitoring & Debugging

### Logs

```bash
bash setup.sh logs api-gateway
docker logs minder-api-gateway --tail 100 -f
```

### Prometheus / Grafana

```bash
# Prometheus targets
curl -s http://localhost:9090/api/v1/targets \
  | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Grafana datasources
curl -s -u admin:admin http://localhost:3000/api/datasources \
  | jq '.[] | {name, type}'
```

### Jaeger (tracing)

```bash
# UI at http://localhost:16686
docker logs minder-jaeger --tail 30
```

---

## Emergency Procedures

### Full restart

```bash
bash setup.sh stop
sleep 5
bash setup.sh start
bash setup.sh status
```

### Backup / restore

```bash
bash setup.sh backup
bash setup.sh restore
```

See [emergency-procedures.md](emergency-procedures.md) for detailed incident runbooks.

---

## Getting Help

```bash
# Collect diagnostics
bash setup.sh status  > /tmp/status.txt
bash setup.sh doctor  > /tmp/doctor.txt
docker stats --no-stream > /tmp/stats.txt
docker ps -a > /tmp/containers.txt

# Quick triage
docker ps -a | grep -i "restarting\|exited"   # problem containers
df -h                                          # disk space
docker system df                               # docker disk usage
```

---

## Additional Resources

- [Common Issues](common-issues.md)
- [Emergency Procedures](emergency-procedures.md)
- [Development Guide](../development/development.md)

---

*Last Updated: 2026-07-10 · Platform Version: 1.0.0 · Development environment (RPi-4)*
