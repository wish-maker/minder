# Common Issues

**Last Updated:** 2026-07-10
**Platform Version:** 1.0.0

Common problems and solutions for the Minder platform (development environment, Raspberry
Pi 4, 31 containers). Services run as Docker containers named `minder-<service>`. Compose is
at `docker/compose/docker-compose.yml`; the root `./.env` is the single source of truth for
configuration.

For the broader guide, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

## Service Won't Start

### Service immediately exits

```bash
# Check logs
docker logs minder-<service> --tail 100
# or
cd docker/compose && docker compose logs <service>
```

Common causes:
1. Configuration error or missing environment variable (check root `./.env`)
2. A dependency (postgres/redis/qdrant/neo4j) not ready yet
3. Port conflict on the host
4. Insufficient resources (this is a Pi — RAM is tight)

### Recreate a service after fixing config

```bash
cd docker/compose
docker compose up -d --force-recreate <service>
# or
bash setup.sh restart <service>
```

### Port conflict on the host

```bash
# Find what holds the port (host-exposed app services use 8000-8006, 8008)
lsof -i :8000

# Stop the offending process, or adjust the mapping in docker-compose.yml
```

---

## A Service Shows "no-healthcheck" — Is It Broken?

Usually **no**. Three containers have **no healthcheck by design** because their base
images lack the required tooling:

- `minder-otel-collector`
- `minder-redis-exporter`
- `minder-rabbitmq-exporter`

`docker ps` will show them with no health status. That is expected — it is not an
"unhealthy" state. Confirm they work by their logs/metrics, not by health:

```bash
docker logs minder-otel-collector --tail 30
docker logs minder-redis-exporter --tail 30
docker logs minder-rabbitmq-exporter --tail 30
```

(Older docs incorrectly listed `redis-exporter` / `otel-collector` as "unhealthy". They are
not — they just have no healthcheck.)

---

## Database Issues

### Can't connect to PostgreSQL

```bash
# Is it up and accepting connections?
docker exec minder-postgres pg_isready -U minder
docker exec minder-postgres psql -U minder -c "SELECT 1;"

# Logs
docker logs minder-postgres --tail 50
```

### Migration failed

```bash
# Re-run migrations
bash setup.sh migrate

# Or apply a SQL file directly
docker exec -i minder-postgres psql -U minder -d minder < migration.sql
```

### Fresh reset (WARNING: destroys data)

```bash
cd docker/compose
docker compose down -v
bash setup.sh start
```

---

## Redis Authentication

**Symptom:**

```
AUTH failed: WRONGPASS invalid username-password pair or Redis is loading from disk
```

**Cause:** the password used doesn't match the one Redis is running with.

**Fix / verify:**

```bash
# Confirm the password in the root .env (source of truth)
grep REDIS_PASSWORD .env

# Test with it
docker exec minder-redis redis-cli -a "$REDIS_PASSWORD" ping   # -> PONG

# If needed, restart Redis
cd docker/compose && docker compose restart redis
docker logs minder-redis --tail 50
```

Remember: edit the **root `./.env`**, not `docker/compose/.env` (the latter is regenerated
from the root file by `setup.sh` on every start/restart).

---

## Neo4j Not Ready

Neo4j takes time to start. It is used by the marketplace (plugin dependency graph) and by
graph-rag (knowledge graph).

```bash
# Wait for it to finish starting
docker logs minder-neo4j --tail 50 | grep -i "started\|remote interface"

# Test a query
docker exec minder-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;"

# Check the password
grep NEO4J .env
```

---

## Plugin Not Loading

Plugins are managed by the plugin-registry service (`:8001`). Note that **no default
plugins are shipped** — an empty plugin list is expected on a clean install.

```bash
# Registry health and plugin list
curl http://localhost:8001/health
curl http://localhost:8001/plugins

# Registry logs
docker logs minder-plugin-registry --tail 50
```

See [../development/plugin-development.md](../development/plugin-development.md) for the
plugin model (manifest-based, no arbitrary code execution).

---

## Memory / Resource Pressure

```bash
# Per-container usage
docker stats --no-stream

# Reclaim space from unused Docker resources
docker system prune -a

# Look for OOM kills
docker logs minder-<service> | grep -i "memory\|oom\|out of"
```

On the Pi, the AI services (rag-pipeline, model-management) and Ollama inference are the
heaviest. Stop non-critical services temporarily if the host is starved.

---

## Network / Services Can't Communicate

```bash
# Network exists?
docker network ls | grep minder

# Service-to-service check (by container name)
docker exec minder-api-gateway curl -s http://minder-rag-pipeline:8004/health

# Bring the stack back consistently
bash setup.sh restart
```

Services address each other by container name on `minder-network`.

---

## Traefik / Routing Returns 404

Minder uses **Traefik v3** (not Nginx). Only services with the right Docker labels are
routed (`exposedByDefault: false`).

```bash
docker logs minder-traefik --tail 50
cd docker/compose && docker compose restart traefik
```

Note: Authelia forward-auth is wired on several routers but **Authelia is disabled**, so
that auth is not currently enforced — you will not be redirected to a login page.

---

## Slow API Responses

```bash
# Resource usage
docker stats --no-stream

# Turn up logging: set LOG_LEVEL=DEBUG in the root ./.env, then
bash setup.sh restart <service>

# Check DB connection count
docker exec minder-postgres psql -U minder -c \
  "SELECT count(*) FROM pg_stat_activity;"
```

---

## Getting Help

```bash
# Collect diagnostics
bash setup.sh status > /tmp/status.txt
bash setup.sh doctor > /tmp/doctor.txt
docker ps -a > /tmp/containers.txt
docker stats --no-stream > /tmp/stats.txt
```

### Useful commands

```bash
docker ps                               # service status
docker stats --no-stream                # resource usage
docker logs minder-<service> --tail 50  # service logs
bash setup.sh restart <service>         # restart a service
bash setup.sh doctor                    # environment diagnostics
```

### Emergency reset (WARNING: deletes all data)

```bash
cd docker/compose
docker compose down -v
docker system prune -a
bash setup.sh start
```
