# Development Guide

**Last Updated:** 2026-07-10

## Overview

This guide covers local development setup, workflow, and conventions for the Minder
platform. Minder is a set of Python (3.11 / 3.12) FastAPI services orchestrated with
Docker Compose, fronted by the **Traefik** reverse proxy. There is **no separate frontend
app** — the web UI is **OpenWebUI**.

## Prerequisites

### Required Software

- **Docker** and **Docker Compose v2** — container runtime and orchestration
- **Git** — version control
- **Python 3.11+** — required: the `setup.sh` CLI is native Python (`python -m scripts.setup`;
  `setup.sh` is a thin shim). Also used for running a service or tests outside Docker.
- An editor of your choice (VS Code, PyCharm, etc.)

### Recommended Tools

- **curl** / **httpie** — API testing

## Layout

```
minder/
├── setup.sh                       # single entry point for all lifecycle commands
├── pyproject.toml                 # Python tooling config (black, isort, pytest, mypy)
├── docker-compose.test.yml        # test dependencies
├── docker/
│   └── compose/
│       └── docker-compose.yml     # hand-maintained source of truth for services
├── src/
│   ├── services/                  # one FastAPI app per service (see below)
│   ├── core/                      # shared core logic (plugin interface, loaders)
│   ├── plugins/                   # plugin implementations
│   ├── shared/                    # shared helpers/utilities
│   └── requirements/              # shared dependency pins
└── tests/                         # unit / integration / e2e / performance / manual
```

### Services (`src/services/`)

Eight FastAPI services:

| Directory | Container | Host Port |
|-----------|-----------|-----------|
| `api-gateway` | minder-api-gateway | 8000 |
| `plugin-registry` | minder-plugin-registry | 8001 |
| `marketplace` | minder-marketplace | 8002 |
| `plugin-state-manager` | minder-plugin-state-manager | 8003 |
| `rag-pipeline` | minder-rag-pipeline | 8004 |
| `model-management` | minder-model-management | 8005 |
| `tts-stt` | minder-tts-stt | 8006 |
| `graph-rag` | minder-graph-rag | 8008 |

Most services build on `python:3.12-slim`; `graph-rag` uses `python:3.11-slim`.

## Local Development Setup

### Quick Start

```bash
# Clone
git clone git@github.com:wish-maker/minder.git
cd minder

# Create the environment file (root ./.env is the single source of truth)
cp .env.example .env

# Start everything (setup.sh auto-fills any CHANGEME secret with a secure random
# value, then mirrors ./.env → docker/compose/.env and brings the stack up)
bash setup.sh start

# Check status
bash setup.sh status
```

### Environment Configuration

The **root `./.env` is the single source of truth**. `setup.sh` mirrors it to
`docker/compose/.env` (auto-generated — do **not** edit that copy). You do not need to
generate secrets by hand: `setup.sh` fills every `CHANGEME` placeholder with a secure
random value on install/start/restart and leaves any value you set yourself untouched.

Set non-secret dev options directly in `./.env`, e.g.:

```bash
ENVIRONMENT=development
LOG_LEVEL=DEBUG
```

### setup.sh commands

`setup.sh` is the single entry point:

```
install | start | stop | restart | status | logs | shell | migrate |
backup | restore | doctor | update | ollama-mode | sync-postgres-password | uninstall
```

Common usage:

```bash
bash setup.sh start          # bring the stack up
bash setup.sh status         # health overview
bash setup.sh logs <svc>     # tail a service's logs
bash setup.sh restart <svc>  # restart a service
bash setup.sh doctor         # environment / dependency diagnostics
bash setup.sh shell <svc>    # shell into a service container
```

Under the hood, Compose is invoked as:

```bash
docker compose --file docker/compose/docker-compose.yml <command>
```

### Bringing up individual services (advanced)

`setup.sh start` is the normal path. If you need to bring up a subset manually, use the
compose file directly:

```bash
docker compose -f docker/compose/docker-compose.yml up -d postgres redis qdrant neo4j
docker compose -f docker/compose/docker-compose.yml up -d api-gateway rag-pipeline
```

## Development Workflow

### Feature Development

```bash
git checkout -b feature/my-change
# ... edit code ...
pytest tests/unit/ -v
black src/ && isort src/
git add -A
git commit -m "feat(scope): describe the change"
```

### Adding a New Service

```bash
# Create the service package
mkdir -p src/services/new-service
cd src/services/new-service
touch main.py config.py Dockerfile

# Add a service definition to docker/compose/docker-compose.yml
# (this file is hand-maintained — edit it directly)

# Build and start
docker compose -f docker/compose/docker-compose.yml up -d --build new-service
```

**Minimal FastAPI service:**

```python
# main.py
from fastapi import FastAPI

from config import settings

app = FastAPI(title="New Service", version="1.0.0")


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "new-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8009)
```

### Adding an API Endpoint

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/plugins", tags=["plugins"])


@router.post("/")
async def create_plugin(plugin: PluginCreate):
    ...
    return {"id": "123", "status": "created"}
```

## Testing

See [testing.md](testing.md) for the full guide. Quick reference:

```bash
pytest tests/unit/ -v          # unit tests
pytest tests/integration/ -v   # integration tests (needs docker-compose.test.yml deps)
pytest --cov=src --cov-report=term-missing
```

pytest uses `asyncio_mode = "auto"` (root `pyproject.toml`), so async tests need no
explicit marker.

## Code Quality

Config lives in the **root `pyproject.toml`**; CI (`quality.yml`) enforces it. See
[code-style.md](code-style.md).

```bash
black src/                 # format (line length 88)
isort src/                 # sort imports (black profile)
mypy src/                  # type check
```

## Debugging

### View Logs

```bash
# Via setup.sh
bash setup.sh logs api-gateway

# Directly
docker logs minder-api-gateway --tail 100 -f
docker logs minder-api-gateway --since 1h
```

### Enter a Container

```bash
bash setup.sh shell api-gateway
# or
docker exec -it minder-api-gateway bash
```

### Resource Usage

```bash
docker stats --no-stream
```

## Working with Storage Backends

Storage services are **internal-only** (not exposed on host ports). Reach them by exec'ing
into their container.

### PostgreSQL

```bash
docker exec -it minder-postgres psql -U minder
# \l   list databases   \dt  list tables
```

Auxiliary databases exist alongside the main DB (e.g. `minder_marketplace`,
`minder_schemaregistry`, and per-domain DBs).

### Redis

```bash
docker exec -it minder-redis redis-cli -a "$REDIS_PASSWORD"
```

### Qdrant / Neo4j

```bash
docker exec -it minder-qdrant sh
docker exec -it minder-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD"
```

## Database Migrations

```bash
# Apply migrations
bash setup.sh migrate

# Or run a SQL file directly
docker exec -i minder-postgres psql -U minder -d minder < migration.sql
```

## Git Workflow

### Commit Conventions

Conventional Commits (see [code-style.md](code-style.md)):

```
feat: add graph-rag entity extraction endpoint
fix: resolve rate limiter fail-open edge case
docs: update development guide
refactor: simplify plugin loader
test: add rag-pipeline integration tests
chore: bump third-party image versions
ci: consolidate workflows
```

### Pull Request Process

1. Branch from `main`
2. Make focused changes
3. Run tests: `pytest tests/unit/ -v`
4. Run formatters/linters: `black src/ && isort src/ && mypy src/`
5. Push and open a PR
6. Address review feedback and merge

## Security Notes (development)

This is a development environment; production hardening is not yet applied. Still:

- **Never hardcode credentials** — read from environment / `./.env`.
- **Validate all inputs** with Pydantic models.
- **Use parameterized queries** — never string-format SQL.

Authentication in api-gateway is **JWT + bcrypt** with Redis-backed rate limiting. There is
**no RBAC** implemented (JWT auth only). The Authelia SSO component is currently disabled
(commented out in compose); auth via Traefik forward-auth is therefore not enforced.

## Resources

### External
- [FastAPI](https://fastapi.tiangolo.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [Pydantic](https://docs.pydantic.dev/)
- [pytest](https://docs.pytest.org/)

### Internal
- [Code Style Guide](code-style.md)
- [Testing Guide](testing.md)
- [Plugin Development](plugin-development.md)
- [Troubleshooting](../troubleshooting/troubleshooting.md)

## Best Practices Summary

1. Use `bash setup.sh` for lifecycle operations
2. Edit the root `./.env`, never `docker/compose/.env`
3. Edit `docker/compose/docker-compose.yml` directly (it is the source of truth)
4. Write tests for new behavior
5. Run `black` / `isort` / `mypy` before pushing
6. Use type hints and Pydantic validation
7. Keep commits focused; use Conventional Commits
