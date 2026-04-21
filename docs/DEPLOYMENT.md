# Minder Platform - Deployment Guide

> **Last Updated:** 2026-04-22
> **Platform Version:** 2.0.0
> **Environment:** Development/Production

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Quick Start](#quick-start)
3. [Environment Configuration](#environment-configuration)
4. [Deployment Options](#deployment-options)
5. [Production Deployment](#production-deployment)
6. [Monitoring & Maintenance](#monitoring--maintenance)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements

**Minimum:**
- CPU: 4 cores
- RAM: 8 GB
- Disk: 20 GB free space
- OS: Linux (Ubuntu 22.04+ recommended), macOS, or Windows with WSL2

**Recommended:**
- CPU: 8 cores
- RAM: 16 GB
- Disk: 50 GB SSD
- OS: Ubuntu 22.04 LTS or Docker-optimized Linux

### Software Requirements

- Docker Engine 24.0+
- Docker Compose v2.20+
- Git 2.30+
- curl (for testing)
- Python 3.11+ (for local development)

---

## Quick Start

### 1. Clone Repository

```bash
git clone https://github.com/your-org/minder.git
cd minder
```

### 2. Configure Environment

```bash
cd infrastructure/docker
cp .env.example .env
# Edit .env with your configuration
nano .env
```

**Required Environment Variables:**

```bash
# Database
POSTGRES_PASSWORD=change_me_production_password

# Redis
REDIS_PASSWORD=change_me_redis_password

# JWT
JWT_SECRET=change_me_jwt_secret_key_min_32_chars

# Application
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### 3. Start All Services

```bash
# Start Phase 1-3 services
docker compose up -d

# Wait for services to be healthy (30-60 seconds)
docker compose ps
```

### 4. Verify Deployment

```bash
# Check health status
curl http://localhost:8000/health | jq '.'

# Check all services
curl http://localhost:8001/health | jq '.'  # Plugin Registry
curl http://localhost:8004/health | jq '.'  # RAG Pipeline
curl http://localhost:8005/health | jq '.'  # Model Management
```

### 5. Access Services

- **API Gateway:** http://localhost:8000
- **Plugin Registry:** http://localhost:8001
- **RAG Pipeline:** http://localhost:8004
- **Model Management:** http://localhost:8005
- **Prometheus:** http://localhost:9090
- **Grafana:** http://localhost:3000 (admin/admin)

---

## Environment Configuration

### Development Environment

```bash
# Use default configuration
cd infrastructure/docker
docker compose up -d
```

### Production Environment

```bash
# Create production .env
cat > .env <<EOF
# Database
POSTGRES_PASSWORD=$(openssl rand -hex 32)
REDIS_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

# Application
LOG_LEVEL=WARNING
ENVIRONMENT=production
RATE_LIMIT_PER_MINUTE=100
RATE_LIMIT_BURST=200
EOF

# Start services
docker compose --profile monitoring up -d
```

### External Services (Optional)

```bash
# Start with external Qdrant
docker compose -f docker-compose.yml -f docker-compose.external.yml up -d
```

---

## Deployment Options

### Option 1: Docker Compose (Development/Small Production)

**Pros:**
- Simple setup
- Easy local development
- Good for single-server deployments

**Cons:**
- Single point of failure
- Limited scalability
- Manual scaling required

**Commands:**
```bash
cd infrastructure/docker
docker compose up -d
```

### Option 2: Kubernetes (Production)

**Pros:**
- Auto-scaling
- Self-healing
- Rolling updates
- Multi-node deployment

**Cons:**
- Complex setup
- Requires Kubernetes cluster
- Higher operational overhead

**Status:** Planned for Phase 4

### Option 3: Cloud Platforms (AWS/GCP/Azure)

**Deployment Options:**
- AWS ECS/EKS
- GCP Cloud Run/GKE
- Azure Container Instances/AKS

**Requirements:**
- Container registry
- Load balancer
- Managed database
- Environment variable management

---

## Production Deployment

### 1. Security Hardening

**Generate Secure Passwords:**

```bash
# Generate random passwords
POSTGRES_PASSWORD=$(openssl rand -hex 32)
REDIS_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)

# Update .env file
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$POSTGRES_PASSWORD/" .env
sed -i "s/REDIS_PASSWORD=.*/REDIS_PASSWORD=$REDIS_PASSWORD/" .env
sed -i "s/JWT_SECRET=.*/JWT_SECRET=$JWT_SECRET/" .env
```

**Configure Firewall:**

```bash
# Allow only required ports
ufw allow 80/tcp    # HTTP (reverse proxy)
ufw allow 443/tcp   # HTTPS (reverse proxy)
ufw allow 8000/tcp  # API Gateway (if direct access)
ufw allow 3000/tcp  # Grafana
ufw allow 9090/tcp  # Prometheus (internal only recommended)
ufw enable
```

### 2. Resource Limits

**Update docker-compose.yml:**

```yaml
services:
  api-gateway:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 1G
        reservations:
          cpus: '0.5'
          memory: 512M

  rag-pipeline:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
```

### 3. Reverse Proxy (Nginx)

**Install Nginx:**

```bash
sudo apt install nginx
```

**Configure Nginx:**

```nginx
# /etc/nginx/sites-available/minder

server {
    listen 80;
    server_name minder.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name minder.example.com;

    ssl_certificate /etc/ssl/certs/minder.crt;
    ssl_certificate_key /etc/ssl/certs/minder.key;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 4. SSL Certificates

**Let's Encrypt (Recommended):**

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d minder.example.com
```

**Self-Signed (Development):**

```bash
# Generate self-signed certificate
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/certs/minder.key \
  -out /etc/ssl/certs/minder.crt
```

### 5. Database Backups

**Automated Backup Script:**

```bash
#!/bin/bash
# /usr/local/bin/backup-minder.sh

BACKUP_DIR="/backups/minder"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

# Backup PostgreSQL
docker exec minder-postgres pg_dump -U minder -d minder | gzip > \
  "$BACKUP_DIR/postgres_$DATE.sql.gz"

# Backup Redis
docker exec minder-redis redis-cli --rdb /data/dump.rdb BGSAVE
docker cp minder-redis:/data/dump.rdb "$BACKUP_DIR/redis_$DATE.rdb"

# Keep last 7 days, delete older
find "$BACKUP_DIR" -type f -mtime +7 -delete
```

**Schedule with Cron:**

```bash
# Daily backup at 2 AM
0 2 * * * /usr/local/bin/backup-minder.sh
```

---

## Monitoring & Maintenance

### Health Checks

**Automated Health Check Script:**

```bash
#!/bin/bash
# /usr/local/bin/health-check.sh

SERVICES=(
    "http://localhost:8000/health"
    "http://localhost:8001/health"
    "http://localhost:8004/health"
    "http://localhost:8005/health"
)

for url in "${SERVICES[@]}"; do
    if ! curl -sf "$url" > /dev/null; then
        echo "ALERT: Service unhealthy - $url"
        # Send notification (Slack, email, etc.)
    fi
done
```

### Monitoring Stack

**Prometheus:** http://localhost:9090
- Metrics collection
- Targets status
- Query interface

**Grafana:** http://localhost:3000
- Default credentials: admin/admin
- **CHANGE PASSWORD ON FIRST LOGIN!**

**Key Metrics to Monitor:**

1. Service health (up/down status)
2. Request rate (requests per second)
3. Request duration (p50, p95, p99 latency)
4. Error rate (4xx, 5xx responses)
5. Resource usage (CPU, memory, disk)

### Log Management

**View Logs:**

```bash
# All services
docker compose logs -f

# Specific service
docker logs minder-api-gateway -f --tail 100

# Last 100 lines
docker logs --tail 100 minder-api-gateway
```

**Centralized Logging (Optional):**

```bash
# ELK Stack (Elasticsearch, Logstash, Kibana)
# Or Loki + Grafana
# Or cloud service (AWS CloudWatch, GCP Cloud Logging)
```

### Updates and Maintenance

**Zero-Downtime Updates:**

```bash
# Pull latest images
docker compose pull

# Update service one at a time
docker compose up -d --no-deps --scale api-gateway=2
docker compose up -d --no-deps api-gateway

# Repeat for each service
```

**Data Migrations:**

```bash
# Backup before migration
/usr/local/bin/backup-minder.sh

# Run migration
docker exec minder-api-gateway python -c "
import asyncio
from src.core.database_migration import DatabaseMigration
asyncio.run(DatabaseMigration.migrate())
"
```

---

## Troubleshooting

### Common Issues

#### 1. Services Won't Start

**Symptoms:**
- Container status: Exited (1)
- Logs show "Connection refused"

**Solutions:**
```bash
# Check port conflicts
sudo netstat -tulpn | grep -E "8000|8001|8004|8005|5432|6379|6333"

# Check disk space
df -h

# Check memory
free -h

# View logs
docker logs <container-name>
```

#### 2. High Memory Usage

**Symptoms:**
- Services slow or unresponsive
- OOM kills in logs

**Solutions:**
```bash
# Restart services
docker compose restart

# Clear Redis cache
docker exec minder-redis redis-cli FLUSHALL

# Reduce Model Management cache size
docker exec minder-model-management rm -rf /app/model-cache/*
```

#### 3. Metrics Not Appearing in Prometheus

**Symptoms:**
- Targets show "down" in Prometheus
- No metrics in Grafana

**Solutions:**
```bash
# Check if metrics endpoint works
curl http://localhost:8000/metrics

# Check Prometheus configuration
docker exec minder-prometheus cat /etc/prometheus/prometheus.yml

# Restart Prometheus
docker restart minder-prometheus

# Check network connectivity
docker exec minder-prometheus wget -qO- http://minder-api-gateway:8000/metrics
```

#### 4. Plugin Load Failures

**Symptoms:**
- Plugin count < 5
- Logs show "Failed to load plugin"

**Solutions:**
```bash
# Check plugin directory permissions
ls -la /root/minder/src/plugins/

# Check plugin configuration
cat /root/minder/src/plugins/*/plugin.yml

# Test plugin manually
cd /root/minder
python -c "
import sys
sys.path.insert(0, 'src')
from plugins.crypto import crypto_module
print(crypto_module.register())
"
```

### Emergency Procedures

**Rollback to Previous Version:**

```bash
# Stop all services
docker compose down

# Start previous version
docker-compose.yml.backup
docker compose up -d
```

**Emergency Backup:**

```bash
# Quick database backup
docker exec minder-postgres pg_dump -U minder -d minder > emergency_backup.sql

# Quick config backup
tar czf config_backup.tar.gz infrastructure/docker/.env infrastructure/docker/*.yml
```

**Disable Failing Service:**

```bash
# Scale problematic service to 0
docker compose up -d --scale rag-pipeline=0
```

---

## Performance Tuning

### Database Optimization

**PostgreSQL Configuration:**

```sql
-- Increase shared buffers
ALTER SYSTEM SET shared_buffers = '256MB';
ALTER SYSTEM SET effective_cache_size = '1GB';
ALTER SYSTEM SET maintenance_work_mem = '256MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- Create indexes for common queries
CREATE INDEX idx_plugins_status ON plugins(status);
CREATE INDEX idx_knowledge_bases_created ON knowledge_bases(created_at);
```

### Redis Optimization

**Configuration:**

```conf
# /usr/local/etc/redis/redis.conf

maxmemory 2gb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

### Application Tuning

**Uvicorn Workers:**

```python
# In CMD of dockerfile
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**Connection Pooling:**

```python
# In service configuration
HTTPX_MAX_CONNECTIONS = 100
HTTPX_MAX_KEEPALIVE_CONNECTIONS = 20
```

---

## Scaling Strategies

### Vertical Scaling

**Increase Resources:**

```yaml
# In docker-compose.yml
services:
  rag-pipeline:
    mem_limit: 8g
    cpus: 4.0
```

### Horizontal Scaling

**Load Balancer Setup:**

```bash
# Start multiple instances
docker compose up -d --scale api-gateway=3 --scale rag-pipeline=2

# Configure load balancer (Nginx example)
upstream api_gateway {
    server minder-api-gateway-1:8000;
    server minder-api-gateway-2:8000;
    server minder-api-gateway-3:8000;
}
```

---

## Security Best Practices

### 1. Secrets Management

**Never Commit Secrets:**

```bash
# Add to .gitignore
.env
*.key
*.crt
*.pem
secrets/
```

**Use Secrets Manager:**

```bash
# Docker Secrets (Swarm mode)
echo "your_secret" | docker secret create jwt_secret -

# Kubernetes Secrets
kubectl create secret generic jwt-secret --from-literal=your_secret
```

### 2. Network Isolation

**Separate Networks:**

```yaml
# In docker-compose.yml
networks:
  frontend:
    driver: bridge
    internal:
      driver: bridge
      internal: true
```

### 3. Runtime Security

**Non-Root User:**
- All containers run as non-root user (appuser:1000) ✅

**Read-Only Filesystems:**
- Core modules mounted read-only where possible ✅

**Resource Limits:**
- CPU and memory limits configured ✅

---

## Backup and Recovery

### Backup Strategy

**Daily Backups:**
- Database dumps (PostgreSQL)
- Redis snapshots
- Configuration files

**Weekly Backups:**
- Full system backup
- Volume snapshots

### Recovery Procedures

**Restore from Backup:**

```bash
# Stop services
docker compose down

# Restore database
gunzip < /backups/minder/postgres_20260422.sql.gz | \
  docker exec -i minder-postgres psql -U minder

# Restore Redis
docker cp /backups/minder/redis_20260422.rdb \
  minder-redis:/data/dump.rdb

# Start services
docker compose up -d
```

---

## Appendix

### A. Environment Variables Reference

**Complete List:** See [Environment Variables](#environment-configuration) section

### B. Port Reference

| Service | Port | Protocol | External Access |
|---------|------|----------|-----------------|
| API Gateway | 8000 | HTTP | Yes (via proxy) |
| Plugin Registry | 8001 | HTTP | No (internal) |
| RAG Pipeline | 8004 | HTTP | No (internal) |
| Model Management | 8005 | HTTP | No (internal) |
| PostgreSQL | 5432 | PostgreSQL | No (internal) |
| Redis | 6379 | Redis | No (internal) |
| Qdrant | 6333 | HTTP | No (internal) |
| Prometheus | 9090 | HTTP | No (internal) |
| Grafana | 3000 | HTTP | Yes (via proxy) |

### C. Useful Commands

```bash
# View logs
docker compose logs -f

# Restart service
docker compose restart <service>

# Update service
docker compose up -d --build <service>

# Scale service
docker compose up -d --scale <service>=3

# Execute command in container
docker exec -it minder-api-gateway bash

# Check resource usage
docker stats

# Prune old images
docker image prune -a
```

---

## Support

For issues or questions:
- GitHub Issues: https://github.com/your-org/minder/issues
- Documentation: /root/minder/docs/
- Status Dashboard: http://localhost:3000 (Grafana)

---

**Last Updated:** 2026-04-22
**Platform Version:** 2.0.0
