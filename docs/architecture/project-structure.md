# Minder Platform - Project Structure Guide

> **Last Updated:** 2026-07-16

## Directory Layout

```
minder/                              # Project root
├── README.md                        # Main project documentation
├── CONTRIBUTING.md                  # Contribution guidelines
├── LICENSE                          # License
├── setup.sh                         # Entrypoint ⭐ — thin shim → `python -m scripts.setup`
├── setup.bash.sh                    # Frozen bash reference (behavior-gate parity only)
├── .env.example                     # Environment template (tracked)
├── .env                             # Single source of truth (gitignored; you edit this)
├── pyproject.toml                   # Python tooling config (black/isort/mypy/pytest)
├── docker-compose.test.yml          # CI / test compose file
│
├── docs/                            # Documentation
│   ├── getting-started/             # Installation & first steps
│   ├── architecture/                # System architecture & roadmap
│   ├── development/                 # Development workflow
│   ├── deployment/                  # Production deployment
│   ├── guides/                      # How-to guides
│   ├── operations/                  # Operational runbooks
│   ├── troubleshooting/             # Common issues
│   └── api/                         # API reference
│
├── docker/                          # Docker configuration
│   ├── compose/                     # Deployment dir (compose runs from here)
│   │   ├── docker-compose.yml       # HAND-MAINTAINED source of truth (31 services)
│   │   ├── docker-compose.override.yml
│   │   ├── .env                     # Auto-generated mirror of root ./.env (gitignored; do not edit)
│   │   ├── rabbitmq/                # rabbitmq config mounted from here
│   │   └── traefik/                 # traefik dynamic config mounted from here
│   └── services/                    # Per-service configs (source of truth)
│       ├── postgres/                # DB init (init.sql)
│       ├── prometheus/              # Metrics config
│       ├── alertmanager/            # Alert routing
│       ├── grafana/                 # Dashboards & datasources
│       ├── telegraf/                # Metrics agent config
│       ├── traefik/                 # Reverse proxy config
│       ├── neo4j/ · ollama/ · influxdb/ · otel-collector/ · rabbitmq/
│       ├── authelia/                # Authelia config (service disabled)
│       └── scripts/                 # Docker helper scripts
│
├── src/                             # Application source
│   ├── services/                    # Microservices (8 core APIs)
│   │   ├── api-gateway/             # API Gateway (port 8000)
│   │   ├── plugin-registry/         # Plugin Registry (port 8001)
│   │   ├── marketplace/             # Marketplace (port 8002)
│   │   ├── plugin-state-manager/    # State Manager (port 8003)
│   │   ├── rag-pipeline/            # RAG Pipeline (port 8004)
│   │   ├── model-management/        # Model Management (port 8005)
│   │   ├── tts-stt/                 # TTS / STT (port 8006)
│   │   └── graph-rag/               # Graph RAG / knowledge graph (port 8008)
│   ├── core/                        # Core framework (incl. config/default_plugins.yml stub)
│   ├── plugins/                     # First-party module plugins (telegraf, network) + _contract.py
│   ├── requirements/                # Shared Python dependency sets (see below)
│   └── shared/                      # Shared utilities (ai, auth, config, models, utils)
│
├── tests/                           # Test suite
│   ├── unit/                        # Unit tests
│   ├── integration/                 # Integration tests
│   ├── e2e/                         # End-to-end tests
│   ├── performance/                 # Performance tests
│   ├── manual/                      # Manual test scripts
│   └── fixtures/                    # Test data
│
└── scripts/                         # Setup & utility scripts
    ├── setup/                       # ⭐ Native-Python setup CLI (python -m scripts.setup)
    ├── lib/                         # Bash reference modules (behavior-gate parity only)
    ├── gate/                        # Behavior gate — verifies python ↔ bash-reference parity
    ├── health-check.sh              # Health monitoring ⭐
    ├── rolling-update.sh            # Rolling updates
    └── validate-installation.sh    # Install validation
    # (secrets are auto-filled by setup.sh into ./.env — no separate generate-secrets step)
```

> **Compose is the source of truth.** `docker/compose/docker-compose.yml` is hand-maintained.
> There is no template/regenerate machinery — edit the compose file directly. `setup.sh` invokes
> Compose as `docker compose --file docker/compose/docker-compose.yml ...`.

> **Shared dependencies live in `src/requirements/`** (`requirements.txt`, `requirements-dev.txt`,
> `requirements-ml.txt`) — not in `src/config/` (that directory was removed). Python tooling
> config (black/isort/mypy/pytest) lives in the root `pyproject.toml`.

## Service Structure

Each microservice follows this structure:

```
services/<service-name>/
├── main.py                      # FastAPI application entry point
├── config.py                    # Configuration management
├── Dockerfile                   # Container build definition
├── requirements.txt             # Python dependencies
├── routes/                      # API route handlers
│   └── __init__.py
├── models/                      # Data models (Pydantic)
│   └── __init__.py
├── core/                        # Business logic
│   └── __init__.py
└── tests/                       # Service-specific tests
    └── __init__.py
```

### Example: API Gateway

```
services/api-gateway/
├── main.py                      # FastAPI app creation
├── config.py                    # Settings, environment vars
├── Dockerfile                   # Multi-stage build
├── requirements.txt             # FastAPI, Redis, etc.
├── routes/
│   ├── __init__.py
│   ├── plugins.py              # Plugin routes
│   ├── health.py               # Health check
│   └── proxy.py               # Request proxy
├── middleware/
│   ├── __init__.py
│   ├── auth.py                 # JWT authentication
│   ├── rate_limit.py           # Rate limiting
│   └── cors.py                 # CORS handling
└── core/
    ├── __init__.py
    └── gateway.py              # Gateway logic
```

## Infrastructure Components

31 containers total (Authelia is defined but disabled and not counted).

**Edge / Security**:
- Traefik (v3) - Reverse proxy, TLS termination, routing
- Authelia - SSO/2FA — **DISABLED** (commented out in compose)

**Data Stores** (internal-only, not host-exposed):
- PostgreSQL 18.4 - Primary database
- Redis 8.8 - Cache, sessions, rate limiting
- Qdrant 1.18 - Vector database for embeddings
- Neo4j 2026.05 (community) - Graph database
- MinIO - S3-compatible object store
- RabbitMQ 4.3 - Async message bus
- Apicurio schema-registry

**Inference**:
- Ollama - Local LLM inference (profile-gated)

**Core APIs** (8):
- API Gateway (8000) - Single entry point
- Plugin Registry (8001) - Plugin discovery/lifecycle
- Marketplace (8002) - Plugin/tool marketplace
- State Manager (8003) - Plugin state + tool execution
- RAG Pipeline (8004) - Retrieval-augmented generation
- Model Management (8005) - Model registry over Ollama
- TTS/STT (8006) - Text-to-speech / speech-to-text
- Graph RAG (8008) - Entity extraction + Neo4j knowledge graph

**Web UI**:
- OpenWebUI - Ollama chat frontend (the only user-facing web app)

**Observability**:
- Prometheus, Grafana, InfluxDB, Telegraf, Alertmanager, Jaeger, OpenTelemetry collector
- Exporters: postgres, redis, rabbitmq, node, cAdvisor, blackbox

## Key Design Principles

### 1. Microservices Architecture

Each service is:
- **Independent**: Can be deployed, scaled, and updated separately
- **Specialized**: Focused on a specific domain
- **Replaceable**: Can be swapped without affecting others
- **Observable**: Has built-in health checks and metrics

### 2. API-First Design

All services expose:
- RESTful API endpoints
- OpenAPI/Swagger documentation
- Health check endpoints (`/health`)
- Structured logging

### 3. Configuration Management

- **Environment-based**: All config via environment variables
- **Secrets management**: Sensitive data in `.env` (gitignored)
- **Default values**: Provided in `.env.example`
- **Validation**: Pydantic models for config validation

### 4. Observability

Every service has:
- **Health checks**: `/health` endpoint
- **Structured logging**: JSON format logs
- **Metrics**: Prometheus-compatible metrics
- **Tracing**: Request ID tracking

### 5. Security

- **Authentication**: JWT-based auth (bcrypt password hashing)
- **Authorization**: JWT validation only — **RBAC is not implemented**
- **SSO / 2FA**: Authelia is present but **disabled** (commented out in compose)
- **Rate limiting**: Redis-based rate limiter (fail-open)
- **Input validation**: Pydantic validators
- **Secrets management**: environment variables only (root `./.env`)
- **Reverse proxy**: Traefik v3 with TLS
- **Network**: storage backends are internal-only; only Traefik and monitoring services expose host ports

## Development Workflow

### Local Development

```bash
# 1. Start all services
./setup.sh

# 2. Start specific service
docker compose -f docker/compose/docker-compose.yml up -d api-gateway

# 3. View logs
docker compose -f docker/compose/docker-compose.yml logs -f api-gateway

# 4. Restart with rebuild
docker compose -f docker/compose/docker-compose.yml up -d --build api-gateway

# 5. Run tests
pytest tests/unit/ -v
```

### Service Development

```bash
# Enter service container
docker exec -it minder-api-gateway bash

# Install new dependencies
pip install new-package
pip freeze > requirements.txt

# Rebuild container
docker compose -f docker/compose/docker-compose.yml build api-gateway
```

### Testing

```bash
# Unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Specific test
pytest tests/unit/test_module_management.py -v

# Integration tests
pytest tests/integration/ -v
```

## File Naming Conventions

### Python Files
- `main.py` - Application entry point
- `config.py` - Configuration
- `models.py` - Pydantic models
- `routes/` - API route handlers
- `core/` - Business logic
- `utils.py` - Utility functions

### Configuration Files
- `Dockerfile` - Container definition
- `requirements.txt` - Dependencies
- `.env.example` - Environment template
- `pytest.ini` - Test configuration

### Documentation Files
- `README.md` - Service overview
- `ARCHITECTURE.md` - System design
- `API.md` - API documentation
- `CHANGELOG.md` - Version history

## Environment Variables

### Required Variables

All services require these in `.env`:
```bash
# Database
POSTGRES_PASSWORD=your_password

# Redis
REDIS_PASSWORD=your_password

# JWT
JWT_SECRET=your_jwt_secret_minimum_32_characters
```

### Service-Specific Variables

Services may have additional variables:
```bash
# RAG / inference
OLLAMA_HOST=http://ollama:11434
QDRANT_HOST=http://qdrant:6333

# Monitoring
INFLUXDB_TOKEN=your_influxdb_token
```

See root `./.env.example` for complete list.

## Build Process

### Docker Images

Each service has a multi-stage Dockerfile:

```dockerfile
# Stage 1: Dependencies
FROM python:3.12-slim as dependencies   # graph-rag uses python:3.11-slim
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Application
FROM python:3.12-slim
COPY --from=dependencies /root/.local /root/.local
COPY ./app ./app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Image Naming

Images follow this pattern:
```
minder/<service-name>:<version>
```

Example:
```
minder/api-gateway:1.0.0
minder/plugin-registry:1.0.0
```

## Data Persistence

### Docker Volumes

Data is stored in named volumes:
```
docker_postgres_data      # Database data
docker_redis_data         # Redis persistence
docker_qdrant_data        # Vector storage
docker_neo4j_data         # Graph database
docker_ollama_data        # LLM models
docker_influxdb_data      # Metrics data
docker_prometheus_data    # Metrics storage
docker_grafana_data       # Dashboard data
```

### Backups

To backup all data:
```bash
# Backup volumes
docker run --rm -v docker_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_backup.tar.gz /data

# Backup specific database
docker exec minder-postgres pg_dump -U minder > backup.sql
```

## Scaling Strategy

### Horizontal Scaling

Stateless services can be scaled:
```bash
# Scale API Gateway to 3 instances
docker compose -f docker/compose/docker-compose.yml up -d --scale api-gateway=3
```

### Resource Limits

Services have resource limits in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      cpus: '0.5'
      memory: 512M
    reservations:
      cpus: '0.25'
      memory: 256M
```

## Monitoring & Debugging

### Health Checks

```bash
# Check all services
./scripts/health-check.sh

# Check specific service
curl http://localhost:8000/health
```

### Logs

```bash
# View all logs
docker compose -f docker/compose/docker-compose.yml logs -f

# View service logs
docker logs minder-api-gateway --tail 100 -f

# Export logs
docker logs minder-api-gateway > api-gateway.log
```

### Diagnostics

```bash
# Run health check
./scripts/health-check.sh

# Container stats
docker stats

# Resource usage
docker system df
```

## Best Practices

### Code Organization

1. **Separation of Concerns**: Clear separation between routes, models, and business logic
2. **DRY Principle**: Shared code in `src/shared/`
3. **Single Responsibility**: Each module has one clear purpose
4. **Interface Segregation**: Small, focused interfaces

### Documentation

1. **API Docs**: Auto-generated with FastAPI
2. **Code Comments**: Complex logic explained
3. **Architecture Docs**: Design decisions documented
4. **Changelog**: Version changes tracked

### Testing

1. **Unit Tests**: Test individual components
2. **Integration Tests**: Test service interactions
3. **E2E Tests**: Test complete workflows
4. **Performance Tests**: Load and stress testing

## Troubleshooting

### Common Issues

**Service won't start**:
```bash
# Check logs
docker logs <service-name>

# Check port conflicts
lsof -i :8000

# Reset service
docker compose -f docker/compose/docker-compose.yml restart <service>
```

**Database connection errors**:
```bash
# Check database is healthy
docker exec minder-postgres pg_isready -U minder

# Reset database
docker compose -f docker/compose/docker-compose.yml down -v
./setup.sh
```

**Memory issues**:
```bash
# Check resource usage
docker stats

# Clean up unused resources
docker system prune -f

# Increase Docker memory limit (Docker Desktop settings)
```

See [troubleshooting.md](../troubleshooting/troubleshooting.md) for more details.

## Contributing

When contributing:
1. Follow the existing code structure
2. Add tests for new features
3. Update documentation
4. Follow PEP 8 style guide
5. Run type checking with mypy

See [CONTRIBUTING.md](../../CONTRIBUTING.md) for guidelines.
