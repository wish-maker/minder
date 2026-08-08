# Service Access Guide - Minder Platform

**Last Updated:** 2026-07-10
**Platform Version:** 1.0.0
**Environment:** Development (Raspberry Pi 4)

---

## Overview

Minder runs 35 defined containers (33 in the common default) behind **Traefik v3** (reverse proxy, TLS, routing via Docker
labels). This guide describes how services are exposed and how to reach them.

> **Reality check.**
> - **Authelia SSO is ENABLED** (#15) — the Traefik forward-auth middleware enforces it on
>   5 routers (minio, api-gateway, grafana, openwebui, jaeger): an unauthenticated request
>   → **302 to the Authelia portal**. Full browser SSO still needs real DNS + TLS on the
>   deploy (see #15 "C").
> - Non-Traefik host ports are bound to **`127.0.0.1`** (#190): reachable ON the host
>   (`http://localhost:<port>`, for ops/health) but **NOT from other machines** — external
>   access is Traefik-only (`:80`/`:443`, Authelia-gated; the `:8081` dashboard stays
>   LAN/IP-whitelisted).
> - The API Gateway also enforces JWT for writes (#47); the other core services are internal.

Access falls into three categories:
1. **Loopback (127.0.0.1)** — reachable on the host at `http://localhost:<port>` (ops/health), not from other machines (#190).
2. **Traefik-routed** — reachable via `*.minder.local` virtual hosts through ports 80/443 (Authelia-gated).
3. **Internal-only** — reachable only from inside the Docker network (or via a Traefik route
   where one exists).

---

## Loopback (127.0.0.1) Services

These publish a host port bound to `127.0.0.1` (#190) — reachable ON the host at
`http://localhost:<port>` (ops/health), not from other machines. External users reach
them through Traefik (Authelia-gated) where a route exists.

### Core API (FastAPI, all with `/docs`)

| Service | Container | Host Port |
|---------|-----------|-----------|
| API Gateway | `minder-api-gateway` | 8000 |
| Plugin Registry | `minder-plugin-registry` | 8001 |
| Marketplace | `minder-marketplace` | 8002 |
| Plugin State Manager | `minder-plugin-state-manager` | 8003 |
| RAG Pipeline | `minder-rag-pipeline` | 8004 |
| Model Management | `minder-model-management` | 8005 |
| TTS / STT | `minder-tts-stt` | 8006 |
| Graph-RAG | `minder-graph-rag` | 8008 |

### Observability & proxy

| Service | Container | Host Port(s) |
|---------|-----------|--------------|
| Grafana | `minder-grafana` | 3000 |
| Prometheus | `minder-prometheus` | 9090 |
| Alertmanager | `minder-alertmanager` | 9093 |
| InfluxDB | `minder-influxdb` | 8086 |
| Jaeger | `minder-jaeger` | 16686 (UI) |
| OTel Collector | `minder-otel-collector` | 14317 (OTLP gRPC), 14318 (OTLP HTTP), 18888 (metrics) |
| Traefik | `minder-traefik` | 80, 443, 8081 (dashboard, IP-whitelisted) |

```bash
# Direct access examples
curl http://localhost:8000/health          # API Gateway
curl http://localhost:8001/plugins         # Plugin Registry
curl http://localhost:8004/health          # RAG Pipeline
# Open http://localhost:3000 for Grafana, http://localhost:16686 for Jaeger
```

---

## Traefik-Routed Services

Traefik routes selected services on `*.minder.local` virtual hosts (via ports 80/443,
`exposedByDefault: false`, so only labeled services are routed):

| Host | Backend |
|------|---------|
| `grafana.minder.local` | Grafana |
| `jaeger.minder.local` | Jaeger UI |
| `chat.minder.local` | OpenWebUI (LLM chat UI) |
| `minio.minder.local` | MinIO console (9001) |
| `rabbitmq.minder.local` | RabbitMQ management UI (15672), IP-whitelisted |
| `neo4j.minder.local` | Neo4j browser (7474), IP-whitelisted |
| `api.minder.local` | API Gateway |

The forward-auth middleware enforces Authelia on these routers (#15/#185): an
unauthenticated request is 302-redirected to the Authelia portal. Because the service
host ports are loopback-only (#190), there is no direct-port bypass either.

To use `.minder.local` hostnames locally, add them to your `/etc/hosts` pointing at the
Traefik host.

---

## Internal-Only Services

These do **not** publish a host port. They are reachable from inside the Docker network by
container name, or (where noted above) via a Traefik route.

| Service | Container | Internal Port(s) | Notes |
|---------|-----------|------------------|-------|
| PostgreSQL | `minder-postgres` | 5432 | Primary + aux databases |
| Redis | `minder-redis` | 6379 | Cache / rate-limit / sessions |
| Qdrant | `minder-qdrant` | 6333 | Vector DB (RAG) |
| Neo4j | `minder-neo4j` | 7687 (bolt), 7474 (http) | Graph DB; 7474 Traefik-routed |
| MinIO | `minder-minio` | 9000 (S3), 9001 (console) | Object store; 9001 Traefik-routed |
| RabbitMQ | `minder-rabbitmq` | 5672 (AMQP), 15672 (mgmt) | Queue; 15672 Traefik-routed |
| Schema Registry | `minder-schema-registry` | 8080 | Apicurio, isolated postgres DB |
| Ollama | `minder-ollama` | 11434 | LLM runtime (profile-gated, local mode only) |
| Exporters (6) | postgres/redis/rabbitmq/node/cadvisor/blackbox | various | Scraped by Prometheus |

```bash
# From inside the Docker network (service name resolves via Docker DNS)
docker exec minder-api-gateway curl http://minder-qdrant:6333/
docker exec minder-api-gateway curl http://minder-postgres:5432
```

---

## Development / Debugging Access

### setup.sh shell

```bash
bash setup.sh shell api-gateway
bash setup.sh shell rag-pipeline
```

### docker exec

```bash
# Health of a service from inside its own container
docker exec minder-api-gateway curl http://localhost:8000/health

# Database shells
docker exec -it minder-postgres psql -U minder
docker exec -it minder-redis redis-cli -a "$REDIS_PASSWORD" ping
```

---

## Troubleshooting

### 404 from Traefik

```bash
docker logs minder-traefik --tail 50
docker ps | grep <service>
```

### Cannot reach an internal service from the host

Internal-only services (postgres, redis, qdrant, ollama, etc.) do not publish host ports by
design. Reach them via `docker exec` into a service container, or via their Traefik route if
one exists.

### Service unreachable

```bash
docker ps -a --filter name=minder-<service>
docker logs minder-<service> --tail 50
cd ~/minder && docker compose --file docker/docker-compose.yml restart <service>
```

Note: `otel-collector`, `redis-exporter`, and `rabbitmq-exporter` ship **without a
healthcheck** by design, so they show as "no-healthcheck" (not "unhealthy").

---

## Additional Resources

- [Security Architecture](./security-architecture.md)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

---

*Last Updated: 2026-07-10 · Development environment*
