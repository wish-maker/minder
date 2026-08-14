# E2E test harness

Real multi-service tests (`#318`): `conftest.py`'s `live_stack` fixture starts
api-gateway, plugin-registry, rag-pipeline, marketplace, model-management, and
graph-rag as real `uvicorn` subprocesses on `127.0.0.1`, wired together the
same way `docker-compose.yml` does — just `localhost` instead of
`minder-<service>` hostnames. No Docker, no image builds; real sockets, real
FastAPI apps, real routing code. A deterministic fake-Ollama stub
(`fake_ollama.py`) stands in for the real thing.

Each service applies its own `schema.sql` at startup (see `core/database.py`
in plugin-registry/plugin-state-manager, `core/auth.py` in api-gateway) — a
bare, empty Postgres database is enough; there's no separate migration step
to run first.

## Running in CI

`ci.yml`'s `e2e-tests` job already does all of this — service containers for
Postgres, Redis, Qdrant, and (since #583) Neo4j, plus the spaCy model
download graph-rag needs. Nothing to set up by hand there.

## Running locally

Start the four backing services with the same credentials `conftest.py`
defaults to (override any of them via the `E2E_*` env vars below if you
already have something running on these ports):

```bash
docker run -d --name e2e-postgres -p 5432:5432 \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=test_password \
  -e POSTGRES_DB=minder_test postgres:16

docker run -d --name e2e-redis -p 6379:6379 redis:7-alpine

docker run -d --name e2e-qdrant -p 6333:6333 qdrant/qdrant:v1.19

docker run -d --name e2e-neo4j -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/test_password neo4j:2026.06.0-community
```

Then, from the repo root:

```bash
export NEO4J_AUTH=neo4j/test_password   # graph-rag's config.py needs this to import at all
pytest tests/e2e/ -v
```

`conftest.py` also symlinks `/app/{src,plugins,services/plugin-registry}` to
the real checkout (every service's `sys.path.insert(0, "/app/src")` is a
container-absolute path) — this needs write access to create `/app`; on a
shared machine where that's not available, run inside a container or grant
yourself that path first.

## Env var overrides

| Var | Default | |
|-----|---------|---|
| `E2E_DB_HOST` / `E2E_DB_PORT` / `E2E_DB_USER` / `E2E_DB_PASSWORD` / `E2E_DB_NAME` | `127.0.0.1` / `5432` / `postgres` / `test_password` / `minder_test` | |
| `E2E_REDIS_HOST` / `E2E_REDIS_PORT` / `E2E_REDIS_PASSWORD` | `127.0.0.1` / `6379` / `test_password` | |
| `E2E_QDRANT_HOST` / `E2E_QDRANT_PORT` | `127.0.0.1` / `6333` | |
| `E2E_NEO4J_HOST` / `E2E_NEO4J_PORT` | `127.0.0.1` / `7687` | graph-rag only; auth comes from `NEO4J_AUTH` (required, not defaulted — see below) |

`NEO4J_AUTH` (format `user/password`) has **no default** — graph-rag's own
`config.py` raises at import time if it's unset, so it must be exported
before running pytest, not just passed as an `E2E_*` override.

## What's deliberately NOT covered here

marketplace normally uses its own `minder_marketplace` Postgres database and
a real Neo4j graph store; neither is wired up for it in this harness (only
graph-rag's env points at the Neo4j started above). marketplace's own
`/health` only checks Postgres, so it starts and reports healthy regardless,
and its `/v1/graph/*` routes return a real connection-error response rather
than crashing — only its install/uninstall/enable/disable/installations
paths (Postgres-only) get real e2e coverage.
