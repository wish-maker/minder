# Minder Deployment Guide

This guide covers deploying Minder in various environments, from local development to production.

## 📋 Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
- [Docker Deployment](#docker-deployment)
- [Environment Configuration](#environment-configuration)
- [Monitoring and Maintenance](#monitoring-and-maintenance)
- [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements

- **CPU**: 4 cores minimum, 8 cores recommended
- **RAM**: 8GB minimum, 16GB recommended
- **Storage**: 50GB minimum, 100GB+ recommended for production
- **OS**: Linux (Ubuntu 20.04+, Debian 11+, RHEL 8+)
- **Docker**: 20.10+
- **Docker Compose**: 2.0+

### External Dependencies

- PostgreSQL 16+
- InfluxDB 2.x
- Qdrant (vector database)
- Redis 7+
- Ollama (for LLM features)

## Local Development

### Quick Start

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Copy environment template
cp .env.example .env

# Edit .env with your configuration
nano .env

# Start all services
docker-compose up -d

# Check service health
docker-compose ps

# View logs
docker-compose logs -f
```

### Accessing Services

- **API**: http://localhost:8000
- **OpenWebUI**: http://localhost:3000
- **Grafana**: http://localhost:3002 (admin/minder123)
- **Prometheus**: http://localhost:9090
- **API Documentation**: http://localhost:8000/docs

### Development Workflow

```bash
# Stop services
docker-compose down

# Rebuild with local changes
docker-compose build --no-cache

# Start services
docker-compose up -d

# Run tests
docker-compose exec minder-api pytest tests/ -v
```

## Production Deployment

### Pre-Deployment Checklist

- [ ] Set strong passwords for all databases
- [ ] Configure JWT_SECRET_KEY with 32+ character random string
- [ ] Set up SSL/TLS certificates
- [ ] Configure firewall rules
- [ ] Set up monitoring and alerting
- [ ] Configure backup strategy
- [ ] Review rate limiting settings
- [ ] Test disaster recovery procedures

### Security Configuration

```bash
# Generate secure secrets
openssl rand -hex 32  # JWT_SECRET_KEY
openssl rand -base64 24  # Database passwords

# Set environment variables in .env
export JWT_SECRET_KEY="<generated-32-char-key>"
export POSTGRES_PASSWORD="<generated-password>"
export INFLUXDB_INIT_PASSWORD="<generated-password>"
export REDIS_PASSWORD="<generated-password>"
```

### Production docker-compose.yml

Key production configurations:

```yaml
services:
  minder-api:
    environment:
      - ENVIRONMENT=production
      - LOG_LEVEL=WARNING
      - JWT_EXPIRE_MINUTES=15  # Shorter sessions
    deploy:
      resources:
        limits:
          cpus: '4.0'
          memory: 8G
        reservations:
          cpus: '2.0'
          memory: 4G
    restart: always
```

### Database Setup

```bash
# Initialize PostgreSQL with multiple databases
docker-compose exec postgres psql -U postgres -c "
  CREATE DATABASE fundmind;
  CREATE DATABASE minder;
"

# Initialize InfluxDB
docker-compose exec influxdb influx setup \
  --username ${INFLUXDB_INIT_USERNAME} \
  --password ${INFLUXDB_INIT_PASSWORD} \
  --org ${INFLUXDB_INIT_ORG} \
  --bucket ${INFLUXDB_INIT_BUCKET}

# Initialize Qdrant collections
docker-compose exec minder-api python -c "
from core.kernel import MinderKernel
import asyncio

async def setup():
    kernel = MinderKernel({})
    await kernel.initialize_databases()

asyncio.run(setup())
"
```

## Docker Deployment

### Building Production Images

```bash
# Build optimized production image
docker build -t minder-api:prod -f Dockerfile .

# Tag for registry
docker tag minder-api:prod registry.example.com/minder-api:2.0.0

# Push to registry
docker push registry.example.com/minder-api:2.0.0
```

### Running with Docker

```bash
# Pull latest image
docker pull wishmaker/minder:latest

# Run with environment file
docker run -d \
  --name minder-api \
  --env-file .env \
  -p 8000:8000 \
  -v /var/lib/minder:/var/lib/minder \
  -v /var/log/minder:/var/log/minder \
  --restart unless-stopped \
  wishmaker/minder:latest
```

### Docker Swarm Deployment

```bash
# Deploy to swarm
docker stack deploy -c docker-compose.prod.yml minder

# Scale services
docker service scale minder_minder-api=3

# View services
docker stack services minder
```

## Environment Configuration

### Required Variables

```bash
# Database Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=fundmind
POSTGRES_USER=postgres
POSTGRES_PASSWORD=<secure-password>

# InfluxDB Configuration
INFLUXDB_HOST=influxdb
INFLUXDB_PORT=8086
INFLUXDB_INIT_USERNAME=minder
INFLUXDB_INIT_PASSWORD=<secure-password>
INFLUXDB_INIT_ORG=minder
INFLUXDB_INIT_BUCKET=metrics

# Qdrant Configuration
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=<secure-password>

# Ollama Configuration
OLLAMA_HOST=ollama
OLLAMA_PORT=11434

# Security
JWT_SECRET_KEY=<32-char-random-string>
JWT_EXPIRE_MINUTES=30

# Network Configuration
LOCAL_NETWORK_CIDR=192.168.68.0/24
TAILSCALE_CIDR=100.64.0.0/10
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# Application
ENVIRONMENT=production
LOG_LEVEL=INFO
```

### Optional Variables

```bash
# GitHub Integration
GITHUB_TOKEN=<your-github-token>

# Plugin Security
PLUGIN_SECURITY_LEVEL=moderate
PLUGIN_TRUSTED_AUTHORS=
PLUGIN_BLOCKED_AUTHORS=
PLUGIN_REQUIRE_SIGNATURE=false
PLUGIN_MAX_SIZE_MB=10

# Grafana
GRAFANA_ADMIN_PASSWORD=<secure-password>
```

## Monitoring and Maintenance

### Health Checks

```bash
# API Health Check
curl http://localhost:8000/health

# Docker Health Check
docker-compose ps

# Service Status
docker-compose exec minder-api curl http://localhost:8000/system/status
```

### Logs

```bash
# View all logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f minder-api

# View last 100 lines
docker-compose logs --tail=100 minder-api

# Export logs
docker-compose logs > minder-logs.txt
```

### Metrics

- **Prometheus**: http://localhost:9090
- **Grafana Dashboards**: http://localhost:3002

Key metrics to monitor:
- API response times
- Plugin health status
- Database connection pools
- Memory usage
- CPU usage
- Request rates

### Backup Strategy

```bash
# PostgreSQL Backup
docker-compose exec postgres pg_dump -U postgres fundmind > backup_$(date +%Y%m%d).sql

# InfluxDB Backup
docker-compose exec influxdb influx backup /backup/$(date +%Y%m%d)

# Qdrant Backup
docker-compose exec qdrant curl http://localhost:6333/collections/snapshot

# Volume Backup
docker run --rm \
  -v minder_postgres_data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz -C /data .
```

### Updates

```bash
# Pull latest changes
git pull origin main

# Update dependencies
pip install -r requirements.txt --upgrade

# Rebuild and restart
docker-compose down
docker-compose build --no-cache
docker-compose up -d

# Run migrations if needed
docker-compose exec minder-api python -m alembic upgrade head
```

## Troubleshooting

### Common Issues

#### API Not Responding

```bash
# Check service status
docker-compose ps

# Check logs
docker-compose logs minder-api

# Restart service
docker-compose restart minder-api
```

#### Database Connection Issues

```bash
# Test PostgreSQL connection
docker-compose exec postgres pg_isready -U postgres

# Test InfluxDB connection
docker-compose exec influxdb influx ping

# Test Redis connection
docker-compose exec redis redis-cli ping
```

#### High Memory Usage

```bash
# Check resource usage
docker stats

# Adjust memory limits in docker-compose.yml
services:
  minder-api:
    deploy:
      resources:
        limits:
          memory: 8G
```

#### Plugin Errors

```bash
# Check plugin status
curl http://localhost:8000/plugins

# View plugin logs
docker-compose logs | grep PLUGIN

# Restart specific plugin
docker-compose restart minder-api
```

### Performance Optimization

```bash
# Enable Prometheus metrics scraping
# Configure in prometheus.yml

# Adjust worker count
# In docker-compose.yml:
environment:
  - WORKERS=4

# Enable caching
# In .env:
REDIS_HOST=redis
REDIS_PORT=6379
```

### Security Hardening

```bash
# Update all images
docker-compose pull

# Scan for vulnerabilities
docker scout wishmaker/minder:latest

# Configure firewall
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 8000/tcp
ufw enable
```

## Production Tips

1. **Use reverse proxy** (Nginx/Traefik) for SSL termination
2. **Enable rate limiting** to prevent abuse
3. **Set up monitoring alerts** in Grafana/Prometheus
4. **Configure log rotation** to prevent disk space issues
5. **Regular backups** with automated testing
6. **Use secrets management** (Vault, AWS Secrets Manager)
7. **Implement CI/CD pipeline** for automated deployments
8. **Document custom configurations** for your environment

## Support

- **Documentation**: https://github.com/wish-maker/minder#readme
- **Issues**: https://github.com/wish-maker/minder/issues
- **Discussions**: https://github.com/wish-maker/minder/discussions

---

Last updated: April 17, 2026
