# Quick Start Guide

## 5-Minute Setup

### Prerequisites Check
```bash
# Verify Docker is installed
docker --version
docker compose version

# Verify Docker is running
docker ps
```

### Installation

#### Option 1: Automated (Recommended)

The enhanced `setup.sh` script provides complete lifecycle management:

```bash
# Clone and setup
git clone https://github.com/wish-maker/minder.git
cd minder
./setup.sh
```

**That's it!** The platform will be fully operational in ~9 minutes with:
- ✅ Automatic AI model downloads (llama3.2 + nomic-embed-text)
- ✅ Secure password generation
- ✅ Database initialization
- ✅ Network configuration
- ✅ Health monitoring

#### Option 2: Manual
```bash
# 1. Configure environment
cp infrastructure/docker/.env.example infrastructure/docker/.env

# 2. Start services
docker compose -f infrastructure/docker/docker-compose.yml up -d

# 3. Wait for services to be healthy (~9 minutes)
./setup.sh status  # Check if all services are healthy
```

**Note:** Manual setup requires downloading AI models separately:
```bash
docker exec minder-ollama ollama pull llama3.2
docker exec minder-ollama ollama pull nomic-embed-text
```

### Verification

```bash
# Test all APIs
for port in 8000 8001 8002 8003 8004 8005 8006 8007; do
    echo "Testing port $port..."
    curl -s http://localhost:$port/health | jq -r '.status' 2>/dev/null || echo "Not responding"
done

# Check monitoring
echo "Prometheus: $(curl -s http://localhost:9090/-/healthy > /dev/null && echo 'OK' || echo 'FAIL')"
echo "Grafana: $(curl -s http://localhost:3000/api/health > /dev/null && echo 'OK' || echo 'FAIL')"

# Check security
echo "Authelia: $(curl -s http://localhost:9091/api/health | jq -r '.status' 2>/dev/null || echo 'FAIL')"
```

Or use the built-in health check:
```bash
./setup.sh health
```

### Lifecycle Management

The `setup.sh` script provides comprehensive enterprise-grade management:

```bash
# Installation & Lifecycle
./setup.sh                          # Full install (prereqs → env → network → DB → services)
./setup.sh start                    # Start all services
./setup.sh stop                     # Stop all services
./setup.sh stop --clean             # Stop + prune dangling images
./setup.sh restart                  # Restart all services

# Status & Monitoring
./setup.sh status                   # Live health overview + resource usage
./setup.sh status --json            # Machine-readable JSON output
./setup.sh health                   # Run health checks
./setup.sh logs [service]           # Tail logs (all or specific service)

# Operations
./setup.sh shell [service]          # Interactive shell in container
./setup.sh migrate [target]         # Run Alembic DB migrations
./setup.sh doctor                   # Deep diagnostics (disk, ports, secrets, images)

# Data Management
./setup.sh backup                   # Full backup (Postgres, Neo4j, InfluxDB, Qdrant, .env)
./setup.sh restore [archive]        # Restore from backup (interactive if no path)

# Updates
./setup.sh update                   # Pull latest compatible images + rebuild + restart
./setup.sh update --check           # Show available updates without applying

# Uninstallation
./setup.sh uninstall --keep-data    # Remove services, keep data volumes
./setup.sh uninstall --purge        # Stop and DELETE all data (irreversible)

# Help
./setup.sh --help                   # Show all commands with examples
```

### First Steps

1. **Change Default Passwords** ⚠️ **IMPORTANT!**
   ```bash
   # Access Authelia at http://localhost:9091
   # Default credentials: admin / admin123
   # Change immediately after first login!
   ```

2. **Access Services**:
   - **API Gateway**: http://localhost:8000
   - **Plugin Registry**: http://localhost:8001
   - **Marketplace**: http://localhost:8002
   - **AI Services**: http://localhost:8004
   - **OpenWebUI**: http://localhost:8080

3. **View Monitoring**:
   - **Prometheus**: http://localhost:9090
   - **Grafana**: http://localhost:3000 (admin/admin)

### Common Issues

**Port already in use?**
```bash
# Change ports in infrastructure/docker/docker-compose.yml
# Example: ports: - "8080:8000"
```

**Services not starting?**
```bash
# Check logs
./setup.sh logs

# Check status
./setup.sh status

# Restart services
./setup.sh restart
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
# Check for updates
./setup.sh check-updates

# Update images
./setup.sh update
```

### Next Steps

- 📖 Read [Architecture Overview](../architecture/overview.md)
- 🔐 Configure [Authentication & Security](../guides/authentication.md)
- 🔧 See [Development Guide](../development/development.md)
- 🐛 Check [Troubleshooting Guide](../troubleshooting/common-issues.md)
- 📚 See all commands: `./setup.sh --help`
