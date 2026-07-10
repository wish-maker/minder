# Service Access Guide - Minder Platform

**Last Updated:** 2026-07-10
**Platform Version:** 1.0.0
**Environment:** Development (Raspberry Pi 4)

---

## Overview

Minder runs 31 containers behind **Traefik v3** (reverse proxy, TLS, routing via Docker
labels). This guide describes how services are exposed and how to reach them.

> **Reality check.** This is a development environment.
> - **Authelia SSO is DISABLED** (its container is commented out in compose). The Traefik
>   forward-auth middleware is wired on a few routers but **not enforced** — there is no
>   working SSO gate right now.
> - A number of application and observability services **publish host ports directly on the
>   host** (see the map below). They are not all locked behind the proxy.
> - The API Gateway implements its own JWT auth; the other core services do not gate access.

Access falls into three categories:
1. **Host-exposed** — reachable directly at `http://localhost:<port>`.
2. **Traefik-routed** — reachable via `*.minder.local` virtual hosts through ports 80/443.
3. **Internal-only** — reachable only from inside the Docker network (or via a Traefik route
   where one exists).

---

## Host-Exposed Services

These publish a host port and can be reached directly at `http://localhost:<port>`.

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

The forward-auth middleware references Authelia on some of these routers, but since Authelia
is disabled the middleware does **not** currently gate access.

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
cd ~/minder && docker compose --file docker/compose/docker-compose.yml restart <service>
```

Note: `otel-collector`, `redis-exporter`, and `rabbitmq-exporter` ship **without a
healthcheck** by design, so they show as "no-healthcheck" (not "unhealthy").

---

## Additional Resources

- [Security Architecture](./security-architecture.md)
- [Traefik Documentation](https://doc.traefik.io/traefik/)

---

*Last Updated: 2026-07-10 · Development environment*
