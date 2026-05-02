# Minder Platform - Installation Guide

## Prerequisites

### Required Software

- **Docker** 20.10+
- **Docker Compose** 2.20+
- **Git** (for development)

### System Requirements

- **RAM**: 8GB minimum, 16GB recommended
- **Disk**: 20GB free space (+3GB for AI models)
- **CPU**: 4 cores minimum, 8 cores recommended
- **OS**: Linux, macOS, or Windows with WSL2
- **Network**: Stable internet for AI model downloads (first run only)

## Installation Methods

### Method 1: Automated Setup (Recommended)

The `setup.sh` script now provides a complete lifecycle management system for the Minder platform.

```bash
# Clone the repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Run automated setup
./setup.sh
```

That's it! The platform will be fully operational in ~9 minutes with:

**✨ AUTOMATIC FEATURES:**
- 🤖 **AI Models:** Automatically downloads llama3.2 (2GB) and nomic-embed-text (274MB)
- 🔐 **Security:** Generates secure passwords automatically
- 🗄️ **Databases:** Creates and initializes all required databases
- 🌐 **Networking:** Sets up Docker networks automatically

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

This will start 23 services:
- Security Layer (2): Traefik, Authelia
- Core Infrastructure (5): PostgreSQL, Redis, Qdrant, Ollama, Neo4j
- Core APIs (6): API Gateway, Plugin Registry, Marketplace, Plugin State Manager, RAG Pipeline, Model Management
- AI Enhancement (3): TTS/STT Service, Model Fine-tuning, OpenWebUI
- Monitoring Stack (5): InfluxDB, Telegraf, Prometheus, Grafana, Alertmanager
- Metrics Exporters (2): PostgreSQL Exporter, Redis Exporter

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

## Lifecycle Management

The `setup.sh` script provides comprehensive enterprise lifecycle management capabilities:

### Available Commands

```bash
# Installation
./setup.sh                           # Install (default)
./setup.sh install                   # Explicit install

# Service Management
./setup.sh start                    # Start all services
./setup.sh stop                     # Stop all services
./setup.sh stop --clean             # Stop + prune dangling images
./setup.sh restart                  # Restart all services

# Status & Monitoring
./setup.sh status                   # Show detailed service status
./setup.sh status --json            # Machine-readable JSON output
./setup.sh health                   # Run health checks
./setup.sh logs                     # View service logs
./setup.sh logs <service>           # View specific service logs

# Operations
./setup.sh shell <service>          # Interactive shell in container
./setup.sh migrate <target>         # Run Alembic DB migrations
./setup.sh doctor                   # Deep diagnostics (disk, ports, secrets, images, versions)

# Data Management
./setup.sh backup                   # Full backup (Postgres, Neo4j, InfluxDB, Qdrant, .env)
./setup.sh restore <archive>        # Restore from backup (interactive if no path)

# Updates & Maintenance
./setup.sh update                   # Update Docker images
./setup.sh update --check           # Show available updates without applying

# Uninstallation
./setup.sh uninstall --keep-data    # Remove services but keep data
./setup.sh uninstall --purge        # Stop and DELETE all data (irreversible)

# Help
./setup.sh --help                   # Show all available commands
```

### Service Status

The `status` command provides a comprehensive overview:

```bash
./setup.sh status
```

Output includes:
- Running containers with health status
- Port mappings
- Resource usage (CPU, memory)
- Volume information
- Network status

### Update Management

The platform supports automated Docker image updates:

```bash
# Check for available updates
./setup.sh check-updates

# Update all images
./setup.sh update
```

The update process:
1. Checks official Docker images for newer versions
2. Pulls latest images from Docker Hub
3. Rebuilds custom Minder images
4. Prompts for service restart

### Backup & Recovery

Automated backup functionality:

```bash
# Create backup
./setup.sh backup

# Backup includes:
# - Environment configuration (.env file)
# - All databases (PostgreSQL dump)
# - Service configurations
```

Backups are stored in `backups/minder-backup-YYYYMMDD-HHMMSS/` with:
- `env.backup` - Environment configuration
- `databases.sql` - Complete database dump

## Verification

### Check Service Status

```bash
# Using lifecycle script
./setup.sh status

# Or using Docker directly
docker ps
```

All services should show "healthy" status.

### View Logs

```bash
# Using lifecycle script (recommended)
./setup.sh logs                     # All services
./setup.sh logs api-gateway         # Specific service

# Or using Docker Compose directly
docker compose -f infrastructure/docker/docker-compose.yml logs -f
docker compose -f infrastructure/docker/docker-compose.yml logs -f api-gateway
```

### Run Tests

```bash
# Unit tests (115 tests, 98% coverage)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v
```

**Expected Results:**
- ✅ 115 tests passing
- ⏭️ 2 tests skipped (expected)
- ⚠️ 5 warnings (non-critical)
- 📊 98% code coverage

## Expected Startup Timeline

When running `./setup.sh`, expect the following timeline:

**0-2 min:** Infrastructure (PostgreSQL, Redis, Qdrant, Ollama, Neo4j)
**2-3 min:** Security layer (Traefik, Authelia)
**3-5 min:** Core APIs (Gateway, Registry, Marketplace, State)
**5-6 min:** AI services (RAG, Model Management)
**6-7 min:** **AI Model Downloads** (automatic, ~3GB total)
**7-8 min:** Monitoring (Prometheus, Grafana, InfluxDB)
**8-9 min:** AI enhancement (OpenWebUI, TTS/STT, Fine-tuning)

**Final Status:** 23 services, all healthy, ready to use

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
# Using lifecycle script
./setup.sh stop
./setup.sh start

# Or manual reset
docker compose -f infrastructure/docker/docker-compose.yml down -v
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres
```

### Services Not Starting

```bash
# Check service status
./setup.sh status

# View logs for issues
./setup.sh logs

# Restart specific service
docker compose -f infrastructure/docker/docker-compose.yml restart <service>
```

### Docker Image Issues

```bash
# Check for updates
./setup.sh check-updates

# Update images
./setup.sh update

# Force rebuild
docker compose -f infrastructure/docker/docker-compose.yml build --no-cache <service>
```

## Next Steps

- Read [Architecture Overview](../architecture/overview.md) to understand the system
- Configure [Authentication & Security](../guides/authentication.md) - **IMPORTANT!**
- See [API Reference](../api/reference.md) for API documentation
- Follow [Development Guide](../development/development.md) for development setup

## Uninstallation

### Remove Services (Keep Data)

```bash
# Using lifecycle script (recommended)
./setup.sh uninstall --keep-data

# Or manual
docker compose -f infrastructure/docker/docker-compose.yml --profile monitoring down
```

### Remove Everything (Including Data)

```bash
# Using lifecycle script (recommended)
./setup.sh uninstall

# Or manual
docker compose -f infrastructure/docker/docker-compose.yml --profile monitoring down -v
docker volume rm docker_postgres_data docker_redis_data docker_qdrant_data docker_ollama_data
```

## Support

For issues and questions:
- GitHub Issues: https://github.com/wish-maker/minder/issues
- Documentation: See docs/ folder
- Lifecycle Management: Run `./setup.sh --help`
