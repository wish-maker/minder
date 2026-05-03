# Minder Platform - Project Structure Guide

## Directory Layout

```
minder/                              # Project root
├── README.md                       # Main project documentation
├── LICENSE                         # MIT License
├── setup.sh                        # Automated setup script ⭐
├── deploy.sh                       # Full deployment automation
├── install.sh                      # Alternative installation script
│
├── docs/                           # Documentation (8 guides)
│   ├── QUICK_START.md             # 5-minute setup guide
│   ├── INSTALLATION.md            # Detailed installation
│   ├── ARCHITECTURE.md            # System architecture
│   ├── DEVELOPMENT.md             # Development workflow
│   ├── DEPLOYMENT.md              # Production deployment
│   ├── TROUBLESHOOTING.md         # Common issues
│   ├── PROJECT_STRUCTURE.md       # This file
│   └── CONTRIBUTING.md            # Contribution guidelines
│
├── infrastructure/                 # Infrastructure configuration
│   └── docker/
│       ├── docker-compose.yml      # Main compose file (24 services)
│       ├── .env.example           # Environment template
│       ├── .env                   # Actual environment (gitignored)
│       ├── postgres-init.sql      # Database initialization
│       ├── telegraf/              # Monitoring config
│       ├── prometheus/            # Metrics config
│       ├── grafana/               # Dashboards
│       ├── nginx/                 # Reverse proxy
│       └── alertmanager/          # Alert rules
│
├── services/                      # Microservices (9 services)
│   ├── api-gateway/              # API Gateway (port 8000)
│   ├── plugin-registry/          # Plugin Registry (port 8001)
│   ├── marketplace/              # Marketplace (port 8002)
│   ├── plugin-state-manager/     # State Manager (port 8003)
│   ├── rag-pipeline/             # AI Services (port 8004)
│   ├── model-management/         # Model Management (port 8005)
│   ├── tts-stt-service/          # TTS/STT Service (port 8006)
│   ├── model-fine-tuning/        # Fine-tuning (port 8007)
│   └── openwebui/               # Web UI (port 8080)
│
├── src/                          # Shared utilities
│   └── shared/                   # Common modules
│       ├── rate_limiter.py       # Rate limiting
│       ├── validators.py         # Input validation
│       ├── database.py           # Database utilities
│       └── security.py           # Security helpers
│
├── tests/                        # Test suite
│   ├── unit/                    # Unit tests (115 tests, 98% coverage)
│   ├── integration/             # Integration tests
│   └── fixtures/                # Test data
│
├── scripts/                      # Utility scripts
│   ├── health-check.sh          # Health monitoring ⭐
│   ├── diagnostics.sh           # System diagnostics
│   ├── cleanup.sh               # Resource cleanup
│   ├── logs.sh                  # Log viewer
│   ├── admin.sh                 # Admin utilities
│   └── update_libraries.sh      # Dependency updates
│
├── pyproject.toml                # Python project configuration
├── pytest.ini                    # Test configuration
├── mypy.ini                      # Type checking configuration
├── requirements.txt              # Production dependencies
├── requirements-dev.txt          # Development dependencies
└── requirements-ml.txt           # ML/AI dependencies
```

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

### Docker Services (24 total)

**Security Layer** (2):
- Traefik - Reverse proxy, load balancer, SSL termination
- Authelia - SSO, 2FA (TOTP/WebAuthn), access control

**Core Infrastructure** (5):
- PostgreSQL - Primary database
- Redis - Cache, sessions, rate limiting
- Qdrant - Vector database for embeddings
- Ollama - Local LLM inference
- Neo4j - Graph database for dependencies

**Core APIs** (6):
- API Gateway - Single entry point
- Plugin Registry - Plugin discovery
- Marketplace - Plugin marketplace
- State Manager - Plugin state tracking
- AI Services - RAG pipeline
- Model Management - Model versioning

**AI Enhancement** (3):
- TTS/STT Service - Text-to-speech/Speech-to-text
- Model Fine-tuning - LLM fine-tuning
- OpenWebUI - Web-based chat interface

**Monitoring Stack** (7):
- InfluxDB - Time-series metrics
- Telegraf - Metrics collection
- Prometheus - Metrics storage
- Grafana - Visualization dashboards
- Alertmanager - Alert management
- PostgreSQL Exporter - DB metrics
- Redis Exporter - Cache metrics

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

- **SSO**: Authelia single sign-on
- **2FA**: TOTP, WebAuthn support
- **Authentication**: JWT-based auth
- **Authorization**: Role-based access control
- **Rate limiting**: Redis-based rate limiter
- **Input validation**: Pydantic validators
- **Secrets management**: Environment variables only
- **Reverse proxy**: Traefik with SSL/TLS

## Development Workflow

### Local Development

```bash
# 1. Start all services
./setup.sh

# 2. Start specific service
docker compose -f infrastructure/docker/docker-compose.yml up -d api-gateway

# 3. View logs
docker compose -f infrastructure/docker/docker-compose.yml logs -f api-gateway

# 4. Restart with rebuild
docker compose -f infrastructure/docker/docker-compose.yml up -d --build api-gateway

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
docker compose -f infrastructure/docker/docker-compose.yml build api-gateway
```

### Testing

```bash
# Unit tests
pytest tests/unit/ -v

# With coverage
pytest tests/ --cov=src --cov-report=html

# Specific test
pytest tests/unit/test_rate_limiter.py -v

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
# AI Services
OLLAMA_HOST=http://ollama:11434
QDRANT_HOST=http://qdrant:6333

# Monitoring
INFLUXDB_TOKEN=your_influxdb_token
```

See `infrastructure/docker/.env.example` for complete list.

## Build Process

### Docker Images

Each service has a multi-stage Dockerfile:

```dockerfile
# Stage 1: Dependencies
FROM python:3.11-slim as dependencies
COPY requirements.txt .
RUN pip install --user -r requirements.txt

# Stage 2: Application
FROM python:3.11-slim
COPY --from=dependencies /root/.local /root/.local
COPY ./app ./app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Image Naming

Images follow this pattern:
```
minder/<service-name>:latest
```

Example:
```
minder/api-gateway:latest
minder/plugin-registry:latest
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
docker compose -f infrastructure/docker/docker-compose.yml up -d --scale api-gateway=3
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
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# View service logs
docker logs minder-api-gateway --tail 100 -f

# Export logs
docker logs minder-api-gateway > api-gateway.log
```

### Diagnostics

```bash
# Run diagnostics
./scripts/diagnostics.sh

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
docker compose -f infrastructure/docker/docker-compose.yml restart <service>
```

**Database connection errors**:
```bash
# Check database is healthy
docker exec minder-postgres pg_isready -U minder

# Reset database
docker compose -f infrastructure/docker/docker-compose.yml down -v
./setup.sh
```

**Memory issues**:
```bash
# Check resource usage
docker stats

# Clean up unused resources
./scripts/cleanup.sh

# Increase Docker memory limit (Docker Desktop settings)
```

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for more details.

## Contributing

When contributing:
1. Follow the existing code structure
2. Add tests for new features
3. Update documentation
4. Follow PEP 8 style guide
5. Run type checking with mypy

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
