# Quick Start Guide

## 5-Minute Setup

### Prerequisites Check
```bash
# Verify Docker is installed
docker --version
docker compose version

# Verify Docker is running
docker ps

# Verify Python 3.11+ (the setup CLI is native Python; setup.sh is a thin shim)
python3 --version
```

### Installation

#### Option 1: Automated (Recommended)

`setup.sh` (a thin shim over the native-Python `python -m scripts.setup`) provides
complete lifecycle management:

```bash
# Clone and setup
git clone git@github.com:wish-maker/minder.git
cd minder
bash setup.sh install     # first time
# bash setup.sh start     # subsequent starts
```

**That's it!** The platform provisions itself with:
- ✅ Automatic Ollama model pulls (llama3.2 + nomic-embed-text, internal mode)
- ✅ Secret generation (fills CHANGEME values in `./.env`)
- ✅ Database initialization + Alembic migrations
- ✅ Docker network configuration
- ✅ Env mirror: root `./.env` → `docker/compose/.env`

#### Option 2: Manual
```bash
# 1. Configure environment (root ./.env is the single source of truth)
cp .env.example .env
# fill in the CHANGEME secrets yourself, then mirror to the path Compose reads
# (setup.sh does this copy + auto-fill for you; bypassing it means doing it manually):
cp .env docker/compose/.env

# 2. Start services
docker compose --file docker/compose/docker-compose.yml up -d

# 3. Wait for services to come up
bash setup.sh status
```

**Note:** In internal-Ollama mode, models are auto-pulled from `OLLAMA_PULL_MODELS`.
For a manual start you can pull them yourself (Ollama is internal-only):
```bash
docker exec minder-ollama ollama pull llama3.2
docker exec minder-ollama ollama pull nomic-embed-text
```

### Verification

Core API services are host-exposed on 8000-8006 and 8008. Storage backends and
Ollama are internal-only.

```bash
# Test all core APIs
for port in 8000 8001 8002 8003 8004 8005 8006 8008; do
    echo "Testing port $port..."
    curl -s http://localhost:$port/health | jq -r '.status' 2>/dev/null || echo "Not responding"
done

# Check monitoring
echo "Prometheus: $(curl -s http://localhost:9090/-/healthy > /dev/null && echo 'OK' || echo 'FAIL')"
echo "Grafana: $(curl -s http://localhost:3000/api/health > /dev/null && echo 'OK' || echo 'FAIL')"
```

Or use the built-in status overview:
```bash
bash setup.sh status
```

### Lifecycle Management

The `setup.sh` entrypoint (thin shim → `python -m scripts.setup`) provides comprehensive enterprise-grade management:

```bash
# Installation & lifecycle
bash setup.sh install               # Install and start
bash setup.sh start                 # Start all services
bash setup.sh stop                  # Stop all services
bash setup.sh restart               # Restart all services

# Status & logs
bash setup.sh status                # Service status overview
bash setup.sh logs [service]        # Tail logs (all or specific service)

# Operations
bash setup.sh shell <service>       # Interactive shell in container
bash setup.sh migrate               # Run Alembic DB migrations
bash setup.sh doctor                # Deep diagnostics (disk, ports, secrets, images)
bash setup.sh ollama-mode <mode>    # Switch Ollama internal / external
bash setup.sh sync-postgres-password # Re-sync the Postgres password

# Data management
bash setup.sh backup                # Full backup (Postgres, Neo4j, InfluxDB, Qdrant, .env)
bash setup.sh restore [archive]     # Restore from backup

# Updates & uninstall
bash setup.sh update                # Update images + rebuild + restart
bash setup.sh update --check        # Report version drift only — no changes applied
bash setup.sh uninstall             # Stop the platform, PRESERVE data volumes
bash setup.sh uninstall --purge     # Stop AND DELETE all data volumes (irreversible)
```

### First Steps

1. **Secure your secrets** ⚠️ **IMPORTANT!**
   - All secrets live in the root `./.env` file. `setup.sh` auto-fills any `CHANGEME`
     values with generated ones on install. Authentication is JWT-based at the API
     Gateway (Authelia SSO is defined in compose but currently disabled).

2. **Access services** (host-exposed ports):
   - **API Gateway**: http://localhost:8000
   - **Plugin Registry**: http://localhost:8001
   - **Marketplace**: http://localhost:8002
   - **RAG Pipeline**: http://localhost:8004
   - **Graph-RAG**: http://localhost:8008
   - **OpenWebUI**: reached via Traefik (the container's 8080 is not host-exposed)

3. **View monitoring**:
   - **Prometheus**: http://localhost:9090
   - **Grafana**: http://localhost:3000
   - **Jaeger**: http://localhost:16686

### Common Issues

**Port already in use?**
```bash
# Change ports in docker/compose/docker-compose.yml
# Example: ports: - "8080:8000"
```

**Services not starting?**
```bash
# Check logs
bash setup.sh logs

# Check status
bash setup.sh status

# Restart services
bash setup.sh restart
```

**Memory issues?**
```bash
# Check Docker memory limits
docker system df

# Clean up unused resources
docker system prune -a
```

**Need to update?**
```bash
# Update images
bash setup.sh update
```

### Next Steps

- 📖 Read [Architecture Overview](architecture/overview.md)
- 🤖 Configure [AI Setup](getting-started/ai-setup.md)
- 📚 See [RAG Methods](rag-methods.md)
- 🔧 See [Development Guide](development/development.md)
- 🐛 Check [Troubleshooting Guide](troubleshooting/common-issues.md)

---

**Last Updated:** 2026-07-10
