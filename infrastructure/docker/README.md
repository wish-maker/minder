# Minder Platform - Docker Deployment

This directory contains the Docker Compose deployment configuration for the Minder platform.

## 🐳 Services (32 Containers)

### Core Infrastructure
- **Traefik** - Reverse proxy and load balancer (Port: 80, 443, 8081)
- **Authelia** - SSO authentication (Port: 9091)
- **API Gateway** - Central API gateway (Port: 8000)

### Databases
- **PostgreSQL** - Relational database (Internal network)
- **Redis** - Cache and message broker (Internal network)
- **Neo4j** - Graph database (Internal network)
- **InfluxDB** - Time-series database (Internal network)
- **Qdrant** - Vector database (Internal network)
- **MinIO** - Object storage (Internal network)

### AI Services
- **Ollama** - LLM inference engine (Port: 11434)
- **OpenWebUI** - AI chat interface (Port: 8080)
- **RAG Pipeline** - Retrieval Augmented Generation (Internal network)
- **Model Management** - Model management (Internal network)
- **TTS-STT Service** - Speech/speech-to-text (Port: 8006)
- **Model Fine-tuning** - Model fine-tuning (Port: 8007)

### Messaging
- **RabbitMQ** - Message broker (Port: 15672)

### Observability
- **Prometheus** - Metrics collection (Port: 9090)
- **Grafana** - Visualization (Port: 3000)
- **Jaeger** - Distributed tracing (Port: 16686)
- **Alertmanager** - Alert management (Port: 9093)
- **Telegraf** - Metrics collection agent (Internal network)
- **OTel Collector** - OpenTelemetry collector (Internal network)

### Exporters
- **PostgreSQL Exporter** - DB metrics (Port: 9187)
- **Redis Exporter** - Cache metrics (Port: 9121)
- **RabbitMQ Exporter** - MQ metrics (Port: 9419)
- **Node Exporter** - System metrics (Port: 9100)
- **Blackbox Exporter** - Probe metrics (Port: 9115)
- **cAdvisor** - Container metrics (Port: 8081)

### Application Services
- **Plugin Registry** - Plugin registration (Internal network)
- **Plugin State Manager** - Plugin state (Internal network)
- **Marketplace** - Plugin marketplace (Internal network)
- **Schema Registry** - Schema management (Internal network)

---

## 🚀 Quick Start

### Starting the System

```bash
# Start all services
docker compose up -d

# Check service status
docker ps

# View logs
docker compose logs -f
```

### Stopping the System

```bash
# Stop all services
docker compose down

# Stop while preserving volumes
docker compose down --remove-orphans
```

### Restarting

```bash
# Restart all services
docker compose restart

# Restart a specific service
docker compose restart <service-name>
```

---

## 🔧 Configuration

### Environment Variables

```bash
# Copy and edit .env file
cp .env.example .env

# Generate strong passwords
openssl rand -base64 32  # For AUTHELIA_SECRET
```

### Required Environment Variables

```bash
# Database passwords
POSTGRES_PASSWORD=strong_password
REDIS_PASSWORD=strong_password

# Authelia secrets
AUTHELIA_STORAGE_ENCRYPTION_KEY=strong_secret
AUTHELIA_JWT_SECRET=strong_secret
AUTHELIA_SESSION_SECRET=strong_secret

# Neo4j
NEO4J_AUTH=neo4j/strong_password
```

---

## 📊 Monitoring

### Prometheus
- **URL:** http://localhost:9090
- **What it monitors:** All 32 services
- **Scrape interval:** 15 seconds

### Grafana
- **URL:** http://localhost:3000
- **Default:** admin/admin (CHANGE THIS!)
- **Dashboards:** System overview, service metrics

### Alertmanager
- **URL:** http://localhost:9093
- **Alert groups:** 9
- **Rules:** 45+

---

## 🗄️ Backup

### Automatic Backups
- **Frequency:** Daily at 02:00
- **Retention:** 7 days
- **Location:** `/root/minder/backups/`

### Manual Backup
```bash
# Backup all databases
/root/minder/backups/backup-databases.sh full

# Backup only PostgreSQL
/root/minder/backups/backup-databases.sh postgres

# View backup statistics
/root/minder/backups/backup-databases.sh stats
```

---

## 🔐 Security

### Zero-Trust Architecture
- ✅ Traefik reverse proxy
- ✅ Authelia SSO authentication
- ✅ Internal network isolation
- ✅ SSL/TLS encryption

### Access Control
- **Public access:** public.minder.local
- **Auth required:** *.minder.local
- **2FA required:** admin.minder.local, api.minder.local

---

## 🐛 Troubleshooting

### Container Not Starting
```bash
# Check logs
docker logs <container-name>

# Verify configuration
docker compose config

# Check volumes
docker volume ls
```

### Service Unreachable
```bash
# Check network status
docker network ls
docker network inspect minder-network

# Service health check
curl http://localhost:8000/health
```

### High Resource Usage
```bash
# View resource usage
docker stats

# Check container limits
docker inspect <container-name> | grep -A 10 "HostConfig"
```

---

## 📈 Performance Optimization

### Resource Limits
CPU and memory limits are defined for all containers.
To adjust, edit the `deploy.resources` section in `docker-compose.yml`.

### Scaling
```bash
# Scale a service
docker compose up -d --scale <service-name>=<replicas>

# Example: Scale API Gateway to 3 replicas
docker compose up -d --scale api-gateway=3
```

---

## 🔄 Upgrade

### Safe Upgrade Procedure
1. Create backup: `/root/minder/backups/backup-databases.sh full`
2. Stop system: `docker compose down`
3. Pull images: `docker compose pull`
4. Start system: `docker compose up -d`
5. Check status: `docker ps`

For detailed information: [UPGRADE-RUNBOOK.md](UPGRADE-RUNBOOK.md)

---

## 📚 Additional Documentation

- [General Documentation](../../docs/README.md)
- [Troubleshooting](../../docs/troubleshooting/common-issues.md)
- [Production Deployment](../../docs/deployment/production.md)
- [API Reference](../../docs/api/reference.md)

---

## 🆘 Support

If you experience issues:
1. [Troubleshooting Guide](../../docs/troubleshooting/common-issues.md)
2. [GitHub Issues](https://github.com/wish-maker/issues)
3. [Emergency Procedures](../../docs/troubleshooting/emergency-procedures.md)

---

**Last Updated:** 2026-05-13
**Version:** 1.0.0
**Status:** 🟢 Production Ready
