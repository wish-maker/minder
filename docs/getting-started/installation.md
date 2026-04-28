# Minder Platform - Installation Guide

## Prerequisites

### Required Software

- **Docker** 20.10+ 
- **Docker Compose** 2.20+
- **Git** (for development)

### System Requirements

- **RAM**: 8GB minimum, 16GB recommended
- **Disk**: 20GB free space
- **CPU**: 4 cores minimum, 8 cores recommended
- **OS**: Linux, macOS, or Windows with WSL2

## Installation Methods

### Method 1: Automated Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Run automated setup
./setup.sh
```

That's it! The platform will be fully operational in ~8 minutes.

### Method 2: Manual Setup

#### Step 1: Environment Configuration

```bash
# Create environment file
cp infrastructure/docker/.env.example infrastructure/docker/.env

# Edit environment variables (optional)
nano infrastructure/docker/.env
```

#### Step 2: Start Infrastructure Services

```bash
# Start databases and core infrastructure
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres redis qdrant ollama neo4j
```

#### Step 3: Start Microservices

```bash
# Start all services
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

This will start 24 services:
- Security Layer (2): Traefik, Authelia
- Core Infrastructure (5): PostgreSQL, Redis, Qdrant, Ollama, Neo4j
- Core APIs (6): API Gateway, Plugin Registry, Marketplace, State Manager, AI Services, Model Management
- AI Enhancement (3): TTS/STT Service, Model Fine-tuning, OpenWebUI
- Monitoring (7): Prometheus, Grafana, InfluxDB, Telegraf, Alertmanager, Exporters

#### Step 4: Verify Installation

```bash
# Check all services are healthy
curl http://localhost:8000/health  # API Gateway
curl http://localhost:8001/health  # Plugin Registry
curl http://localhost:8002/health  # Marketplace
curl http://localhost:8003/health  # State Manager
curl http://localhost:8004/health  # AI Services
curl http://localhost:8005/health  # Model Management
curl http://localhost:8006/health  # TTS/STT Service
curl http://localhost:8007/health  # Model Fine-tuning

# Check security layer
curl http://localhost:9091/api/health  # Authelia

# Check monitoring
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health  # Grafana
```

## Verification

### Check Service Status

```bash
docker ps
```

All services should show "healthy" status.

### View Logs

```bash
# All services
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# Specific service
docker compose -f infrastructure/docker/docker-compose.yml logs -f api-gateway
```

### Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v
```

## Troubleshooting

### Port Conflicts

If you have port conflicts, edit the ports in `infrastructure/docker/docker-compose.yml`:

```yaml
ports:
  - "8080:8000"  # Change API Gateway to port 8080
```

### Memory Issues

If you experience memory issues, increase Docker memory limit:

- **Docker Desktop**: Settings → Resources → Memory (8GB+)
- **Linux**: No action needed

### Database Connection Errors

```bash
# Reset database
docker compose -f infrastructure/docker/docker-compose.yml down -v
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres
```

## Next Steps

- Read [Architecture Overview](../architecture/overview.md) to understand the system
- Configure [Authentication & Security](../guides/authentication.md) - **IMPORTANT!**
- See [API Reference](../api/reference.md) for API documentation
- Follow [Development Guide](../development/development.md) for development setup

## Uninstallation

```bash
# Stop and remove all services
docker compose -f infrastructure/docker/docker-compose.yml down -v

# Remove volumes (WARNING: Deletes all data)
docker volume rm minder_postgres_data minder_redis_data minder_qdrant_data
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/your-org/minder/issues
- Documentation: See docs/ folder
