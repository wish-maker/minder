# Production Deployment Guide

## Overview

This guide covers deploying Minder Platform to production environments.

## Pre-Deployment Checklist

### Environment Variables

- [ ] Review all environment variables in `infrastructure/docker/.env`
- [ ] Generate strong, unique passwords (use `openssl rand -base64 32`)
- [ ] Set `ENVIRONMENT=production`
- [ ] Configure `JWT_SECRET` (minimum 64 characters)
- [ ] Set `LOG_LEVEL=INFO` or `WARNING`

### Security

- [ ] Change all default passwords (**IMPORTANT!**)
- [ ] Change Authelia default passwords (admin/admin123)
- [ ] Configure SMTP for Authelia notifications
- [ ] Enable 2FA for all users
- [ ] Configure SSL/TLS certificates
- [ ] Set up firewall rules
- [ ] Configure backup strategy
- [ ] Review CORS settings
- [ ] Enable rate limiting
- [ ] Review access control rules

### Infrastructure

- [ ] Verify system requirements (8GB+ RAM, 4 CPU cores)
- [ ] Ensure Docker 20.10+ is installed
- [ ] Configure reverse proxy (Nginx/Traefik)
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Configure log aggregation
- [ ] Plan backup strategy

## Deployment Methods

### Method 1: Automated Deployment (Recommended)

```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Run deployment script
./deploy.sh
```

The `deploy.sh` script handles:
1. Environment validation
2. Secure configuration generation
3. Database initialization
4. Service startup
5. Health verification
6. Monitoring setup

### Method 2: Manual Deployment

#### Step 1: Configure Environment

```bash
# Create environment file
cp infrastructure/docker/.env.example infrastructure/docker/.env

# Edit with production values
nano infrastructure/docker/.env
```

Critical variables:
```bash
# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 32)
REDIS_PASSWORD=$(openssl rand -base64 32)
JWT_SECRET=$(openssl rand -base64 64)
INFLUXDB_TOKEN=$(openssl rand -base64 32)

# Set production environment
ENVIRONMENT=production
LOG_LEVEL=INFO
```

#### Step 2: Start Services

```bash
# Start security layer (Traefik + Authelia)
docker compose -f infrastructure/docker/docker-compose.yml up -d traefik authelia

# Wait for security layer (10s)
sleep 10

# Start infrastructure
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres redis qdrant ollama neo4j

# Wait for infrastructure (30s)
sleep 30

# Start core services
docker compose -f infrastructure/docker/docker-compose.yml up -d api-gateway plugin-registry marketplace plugin-state-manager

# Start AI services
docker compose -f infrastructure/docker/docker-compose.yml up -d rag-pipeline model-management

# Start AI enhancement and monitoring
docker compose -f infrastructure/docker/docker-compose.yml up -d openwebui tts-stt-service model-fine-tuning prometheus grafana alertmanager telegraf

# Start metrics exporters
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres-exporter redis-exporter
```
```

#### Step 3: Verify Deployment

```bash
# Run health checks
./scripts/health-check.sh

# Check all APIs
curl http://localhost:8000/health
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8004/health
curl http://localhost:8005/health

# Check monitoring
curl http://localhost:9090/-/healthy  # Prometheus
curl http://localhost:3000/api/health  # Grafana
```

## Production Configuration

### Resource Limits

Edit `infrastructure/docker/docker-compose.yml` to set resource limits:

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
```

### Auto-Restart Policies

All services have:
```yaml
restart: unless-stopped
```

### Health Checks

Services include health checks:
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 40s
```

## Reverse Proxy Configuration

### Traefik Configuration (Recommended)

The Minder platform uses **Traefik v3** as its reverse proxy, which provides:

- **Automatic Service Discovery** - Docker integration, no manual config needed
- **Built-in Load Balancing** - Automatic routing to healthy containers
- **SSL/TLS Termination** - Automatic certificate management
- **Health Checks** - Automatic container health monitoring
- **Middleware Pipeline** - Authentication, rate limiting, headers

**Current Traefik Configuration:**
```yaml
# Already configured in infrastructure/docker/docker-compose.yml
# Traefik Dashboard: http://localhost:8081
# SSL: Auto-generated or configure via Traefik
# Service Discovery: Automatic via Docker labels
```

### Alternative: Manual Nginx (Not Recommended)

If you prefer manual Nginx configuration instead of Traefik:

```nginx
upstream minder_api {
    least_conn;
    server localhost:8000 max_fails=3 fail_timeout=30s;
    server localhost:8001 max_fails=3 fail_timeout=30s;
    server localhost:8002 max_fails=3 fail_timeout=30s;
}

server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://minder_api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### SSL/TLS Setup

**Option 1: Traefik (Recommended)**
- Automatic Let's Encrypt integration
- Certificate auto-renewal
- No manual configuration needed

**Option 2: Manual Certbot (Alternative)**
```bash
# Install certbot
apt-get install certbot python3-certbot-nginx

# Obtain certificate
certbot --nginx -d api.example.com

# Auto-renewal
certbot renew --dry-run
```

## Monitoring Setup

### Prometheus

Access: http://localhost:9090

Configure targets in `infrastructure/docker/prometheus/prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'minder-services'
    static_configs:
      - targets: ['api-gateway:8000', 'plugin-registry:8001']
```

### Grafana

Access: http://localhost:3000

Default credentials:
- Username: `admin`
- Password: `admin` (change on first login)

Import dashboards from `infrastructure/docker/grafana/dashboards/`

### Alertmanager

Access: http://localhost:9093

Configure alerts in `infrastructure/docker/alertmanager/alerts.yml`

## Backup Strategy

### Database Backups

```bash
# Automated daily backup
cat > /etc/cron.d/minder-backup << EOF
0 2 * * * root /path/to/backup-script.sh
EOF

# Backup script
#!/bin/bash
BACKUP_DIR="/backups/minder"
DATE=$(date +%Y%m%d_%H%M%S)

docker exec minder-postgres pg_dump -U minder > "$BACKUP_DIR/postgres_$DATE.sql"
docker exec minder-redis redis-cli --rdb /data/dump.rdb
```

### Volume Backups

```bash
# Backup all volumes
docker run --rm -v docker_postgres_data:/data -v /backups:/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz /data

# Backup to remote
rsync -avz /backups/ user@backup-server:/backups/minder/
```

## Scaling

### Horizontal Scaling

Scale stateless services:
```bash
# Scale API Gateway to 3 instances
docker compose -f infrastructure/docker/docker-compose.yml up -d --scale api-gateway=3

# Scale Plugin Registry
docker compose -f infrastructure/docker/docker-compose.yml up -d --scale plugin-registry=2
```

### Load Balancing

**Traefik (Recommended):**
Traefik automatically handles load balancing across scaled containers using round-robin algorithm.

**Manual Load Balancing (Alternative):**
If you need manual load balancer configuration:

```nginx
upstream api_gateway {
    least_conn;
    server minder-api-gateway-1:8000;
    server minder-api-gateway-2:8000;
    server minder-api-gateway-3:8000;
}
```

**HAProxy (Enterprise Alternative):**
```haproxy
backend api_gateway
    balance roundrobin
    server api-gateway-1:8000 check
    server api-gateway-2:8000 check
    server api-gateway-3:8000 check
```

## Rolling Updates

### Update Services

```bash
# Pull latest code
git pull origin main

# Rebuild specific service
docker compose -f infrastructure/docker/docker-compose.yml build api-gateway

# Rolling update (zero downtime)
docker compose -f infrastructure/docker/docker-compose.yml up -d --no-deps --scale api-gateway=2
docker compose -f infrastructure/docker/docker-compose.yml up -d --no-deps api-gateway
docker compose -f infrastructure/docker/docker-compose.yml up -d --no-deps --scale api-gateway=1
```

## Troubleshooting

### Service Failures

```bash
# Check service status
docker compose -f infrastructure/docker/docker-compose.yml ps

# View logs
docker logs <service-name> --tail 100

# Restart service
docker compose -f infrastructure/docker/docker-compose.yml restart <service>

# Reset service
docker compose -f infrastructure/docker/docker-compose.yml up -d --force-recreate <service>
```

### Performance Issues

```bash
# Check resource usage
docker stats

# Identify bottlenecks
./scripts/diagnostics.sh

# Scale services
docker compose -f infrastructure/docker/docker-compose.yml up -d --scale api-gateway=3
```

### Database Issues

```bash
# Check database health
docker exec minder-postgres pg_isready -U minder

# View connections
docker exec minder-postgres psql -U minder -c "SELECT count(*) FROM pg_stat_activity;"

# Kill long-running queries
docker exec minder-postgres psql -U minder -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active' AND state_change < now() - interval '5 minutes';"
```

## Security Hardening

### Network Security

```bash
# Create isolated network
docker network create --driver bridge minder-internal

# Run services on internal network
# Only API Gateway on external network
```

### Secrets Management

Use Docker Secrets or external vault:
```bash
# Use Docker secrets
echo "your_secret" | docker secret create jwt_secret -

# Reference in compose file
secrets:
  jwt_secret:
    external: true
```

### Access Control

```bash
# Firewall rules
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow from 10.0.0.0/8 to any port 8000

# Rate limiting
# Already configured in API Gateway
```

## Performance Tuning

### Database Optimization

```sql
-- Add indexes
CREATE INDEX idx_plugins_name ON plugins(name);
CREATE INDEX idx_plugins_status ON plugins(status);

-- Configure connection pool
# In docker-compose.yml
environment:
  POSTGRES_POOL_SIZE: 20
  POSTGRES_MAX_CONNECTIONS: 100
```

### Redis Optimization

```bash
# Configure Redis persistence
# In docker-compose.yml
command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD} --maxmemory 256mb --maxmemory-policy allkeys-lru
```

### Application Tuning

```python
# In config.py
class Settings:
    # Connection pools
    DB_POOL_SIZE = 20
    REDIS_POOL_SIZE = 50
    
    # Timeouts
    REQUEST_TIMEOUT = 30
    DATABASE_TIMEOUT = 10
```

## Maintenance

### Regular Maintenance Tasks

```bash
# Clean up unused Docker resources
./scripts/cleanup.sh

# Update dependencies
./scripts/update_libraries.sh

# Restart services
docker compose -f infrastructure/docker/docker-compose.yml restart

# Backup before updates
./scripts/backup.sh
```

### Log Rotation

```bash
# Configure log rotation
cat > /etc/logrotate.d/minder << EOF
/var/log/minder/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 minder minder
}
EOF
```

## Disaster Recovery

### Restore from Backup

```bash
# Stop services
docker compose -f infrastructure/docker/docker-compose.yml down

# Restore volumes
docker run --rm -v /backups:/backup -v docker_postgres_data:/data \
  alpine tar xzf /backup/postgres_20260428.tar.gz

# Restart services
./setup.sh
```

### Emergency Procedures

```bash
# Full system reset
docker compose -f infrastructure/docker/docker-compose.yml down -v
./setup.sh

# Partial reset (specific service)
docker compose -f infrastructure/docker/docker-compose.yml stop <service>
docker compose -f infrastructure/docker/docker-compose.yml rm -f <service>
docker compose -f infrastructure/docker/docker-compose.yml up -d <service>
```

## Support

For production issues:
1. Check logs: `./scripts/logs.sh`
2. Run diagnostics: `./scripts/diagnostics.sh`
3. Review troubleshooting guide: `docs/TROUBLESHOOTING.md`
4. Contact support: support@minder-platform.com
