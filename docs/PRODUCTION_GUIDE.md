# Minder Production Deployment Guide

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Security Configuration](#security-configuration)
4. [Deployment](#deployment)
5. [Monitoring & Alerting](#monitoring--alerting)
6. [Backup & Recovery](#backup--recovery)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 22.04+ or CentOS 8+)
- **RAM**: 4GB minimum, 8GB recommended
- **CPU**: 2 cores minimum, 4 cores recommended
- **Storage**: 20GB free space for databases and logs
- **Network**: Stable internet connection for API integrations

### Software Requirements
- **Docker**: 24.0+ with Docker Compose v2
- **Git**: 2.30+ for repository cloning
- **OpenSSL**: For generating secure secrets

### External Services
- PostgreSQL database (or use Docker container)
- Redis cache (or use Docker container)
- InfluxDB for time-series data (optional)
- Qdrant for vector embeddings (optional)

---

## Environment Setup

### 1. Clone Repository

```bash
git clone https://github.com/wish-maker/minder.git
cd minder
```

### 2. Generate Secure Secrets

**CRITICAL**: Never use default values in production!

```bash
# Generate JWT secret (32+ bytes)
openssl rand -hex 32

# Generate database passwords (24+ bytes)
openssl rand -base64 24

# Generate InfluxDB password
openssl rand -base64 24

# Generate Redis password
openssl rand -base64 24
```

### 3. Configure Environment Variables

Create `.env` file from template:

```bash
cp .env.example .env
nano .env
```

**Required Production Variables:**

```bash
# Security
JWT_SECRET_KEY=<your-32-byte-hex-secret>
JWT_EXPIRE_MINUTES=30
ENVIRONMENT=production

# Database Credentials
POSTGRES_PASSWORD=<your-24-byte-password>
INFLUXDB_PASSWORD=<your-24-byte-password>
REDIS_PASSWORD=<your-24-byte-password>

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
ALLOWED_ORIGINS=https://your-domain.com

# Monitoring
ENABLE_PROMETHEUS=true
ENABLE_ALERTMANAGER=true

# Backup
BACKUP_DIR=/backup/minder
RETENTION_DAYS=7
```

### 4. Configure Application Settings

Edit `config.yaml`:

```yaml
# Production plugin configuration
plugins:
  network:
    enabled: true
    priority: "high"
  
  news:
    enabled: true
    priority: "high"
  
  crypto:
    enabled: true
    priority: "medium"
  
  weather:
    enabled: true
    priority: "medium"
  
  tefas:
    enabled: true
    priority: "low"  # May have connectivity issues
  
  activation_policy:
    strategy: "gradual"
    health_check_interval: 300
    failure_threshold: 3
    auto_restart: true

# Monitoring configuration
monitoring:
  prometheus:
    enabled: true
    port: 9090
  
  grafana:
    enabled: true
    port: 3000
  
  alertmanager:
    enabled: true
    port: 9093
```

---

## Security Configuration

### 1. Password Policies

**Default Requirements:**
- Minimum length: 12 characters
- Must contain: Uppercase, lowercase, digits, special characters
- Common passwords rejected

**To modify policies**, edit `/root/minder/api/auth.py`:

```python
PASSWORD_MIN_LENGTH = 12  # Increase for production
PASSWORD_REQUIRE_UPPERCASE = True
PASSWORD_REQUIRE_LOWERCASE = True
PASSWORD_REQUIRE_DIGIT = True
PASSWORD_REQUIRE_SPECIAL = True
```

### 2. Network Security

**Rate Limiting by Network Type:**
- **Local Network** (192.168.x.x): Unlimited access
- **VPN/Tailscale** (100.x.x.x): 200 requests/hour
- **Public Network**: 50 requests/hour

**Configure allowed networks** in `docker-compose.yml`:

```yaml
environment:
  - RATE_LIMIT_LOCAL=192.168.0.0/16
  - RATE_LIMIT_VPN=100.0.0.0/8
```

### 3. JWT Token Security

**Production Configuration:**
```bash
# Token expiration (30 minutes recommended)
JWT_EXPIRE_MINUTES=30

# Strong secret key (generate with: openssl rand -hex 32)
JWT_SECRET_KEY=<your-secret>
```

### 4. Database Security

**PostgreSQL:**
- Use strong passwords (24+ characters)
- Enable SSL for remote connections
- Restrict network access

**Redis:**
- Require password authentication
- Disable dangerous commands (FLUSHDB, CONFIG)
- Use isolated network

---

## Deployment

### 1. Build Docker Images

```bash
# Build without cache for production
docker compose build --no-cache

# Verify images built
docker images | grep minder
```

### 2. Start Services

```bash
# Start all services
docker compose up -d

# Verify all containers running
docker ps

# Check container health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### 3. Verify Health Checks

```bash
# Check API health
curl http://localhost:8000/health

# Expected response:
{
  "status": "healthy",
  "system": {...},
  "authentication": "enabled",
  "network_detection": "enabled"
}

# Check all plugins healthy
curl http://localhost:8000/system/status
```

### 4. Initial Authentication

**Login with default admin:**

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'
```

**IMPORTANT**: Change default password immediately!

```bash
curl -X POST http://localhost:8000/auth/change-password \
  -H "Authorization: Bearer <your-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "old_password": "admin123",
    "new_password": "<your-strong-password>"
  }'
```

---

## Monitoring & Alerting

### 1. Access Monitoring Interfaces

**Grafana Dashboards:**
- URL: `http://localhost:3000`
- Default credentials: `admin` / `admin` (change on first login)

**Prometheus Metrics:**
- URL: `http://localhost:9090`
- Metrics endpoint: `http://localhost:8000/metrics`

**Alertmanager:**
- URL: `http://localhost:9093`

### 2. Key Metrics to Monitor

**System Health:**
- API response time (< 500ms p95)
- Plugin health status
- Database connection pool
- Memory usage (< 80%)
- CPU usage (< 70%)

**Business Metrics:**
- Records collected per plugin
- Data freshness (last collection time)
- API request rate
- Authentication failures

### 3. Configure Alerts

Edit `alertmanager.yml`:

```yaml
receivers:
  - name: 'pager'
    email_configs:
      - to: 'oncall@your-domain.com'
        from: 'alertmanager@your-domain.com'
        smarthost: 'smtp.gmail.com:587'
        auth_username: 'your-email@gmail.com'
        auth_password: 'your-app-password'

  - name: 'email'
    email_configs:
      - to: 'team@your-domain.com'
        from: 'alertmanager@your-domain.com'
```

**Common Alerts:**
- Container down
- High error rate (> 5%)
- Slow response time (> 1s)
- Plugin data collection failure
- Disk space low (< 20%)

---

## Backup & Recovery

### 1. Automated Backups

**Setup Cron Job:**

```bash
# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /root/minder/scripts/backup.sh

# Add hourly backup for critical data
0 * * * * /root/minder/scripts/backup.sh
```

**Backup Contents:**
- PostgreSQL databases (all)
- InfluxDB time-series data
- Qdrant vector embeddings
- Configuration files (.env, config.yaml)
- Application logs
- Plugin data

**Retention Policy:**
- Default: 7 days
- Configurable via `RETENTION_DAYS` in `.env`

### 2. Manual Backup

```bash
# Run backup manually
cd /root/minder
./scripts/backup.sh

# Verify backup created
ls -lh /backup/minder/ | tail -5
```

### 3. Restore from Backup

**⚠️ WARNING**: Restoration will replace all current data!

```bash
cd /root/minder
./scripts/restore.sh 20240416_020000

# Or restore from latest backup
./scripts/restore.sh latest
```

**Restoration Process:**
1. Validates backup integrity
2. Stops all containers
3. Restores databases
4. Restores configurations
5. Restarts services
6. Verifies health

### 4. Backup Verification

**Regular verification tasks:**

```bash
# Check backup files exist
ls -lh /backup/minder/*/postgres_all.sql.gz

# Verify backup integrity
gunzip -t /backup/minder/*/postgres_all.sql.gz

# Test restoration in staging
./scripts/restore.sh <backup-id> --test-mode
```

---

## Troubleshooting

### Container Issues

**Problem: Container won't start**

```bash
# Check container logs
docker logs minder-api
docker logs postgres
docker logs redis

# Check for port conflicts
netstat -tulpn | grep -E ':(8000|5432|6379)'

# Rebuild container
docker compose down
docker compose build --no-cache <service-name>
docker compose up -d
```

**Problem: Container unhealthy**

```bash
# Check health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# Check health endpoint
curl http://localhost:8000/health

# Check kernel initialization
docker logs minder-api | grep -E "(error|ERROR|failed)"
```

### Database Issues

**Problem: PostgreSQL connection failed**

```bash
# Check PostgreSQL is running
docker exec postgres pg_isready

# Check connection from API container
docker exec minder-api ping -c 2 postgres

# Verify credentials
docker exec postgres psql -U postgres -c "SELECT version();"

# Check database exists
docker exec postgres psql -U postgres -l
```

**Problem: Database locked**

```bash
# Check active connections
docker exec postgres psql -U postgres -c \
  "SELECT pid, usename, query FROM pg_stat_activity WHERE datname = 'fundmind';"

# Terminate long-running queries
docker exec postgres psql -U postgres -c \
  "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE state = 'active';"
```

### Plugin Issues

**Problem: Plugin not loading**

```bash
# Check plugin logs
docker logs minder-api | grep -i plugin

# Verify plugin files exist
ls -la /root/minder/plugins/

# Check plugin configuration
cat /root/minder/config.yaml | grep -A 10 plugins:

# Restart kernel
docker exec minder-api curl -X POST http://localhost:8000/plugins/reload \
  -H "Authorization: Bearer <token>"
```

**Problem: Plugin collecting zero records**

```bash
# Check plugin status
curl http://localhost:8000/plugins | jq .

# Check plugin logs for errors
docker logs minder-api | grep -i <plugin-name>

# Test API connectivity manually
docker exec minder-api curl -I https://api.tefas.org.tr

# Enable debug logging
docker exec -it minder-api bash
export LOG_LEVEL=DEBUG
exit
docker compose restart minder-api
```

### Authentication Issues

**Problem: Cannot login**

```bash
# Verify auth manager initialized
docker logs minder-api | grep "Authentication manager"

# Check default user exists
docker exec minder-api python -c "
from api.auth import auth_manager
print(auth_manager.users)
"

# Reset admin password
docker exec minder-api python -c "
from api.auth import auth_manager
import bcrypt
auth_manager.users['admin']['password_hash'] = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
print('Password reset to admin123')
"
```

**Problem: Token expired quickly**

```bash
# Check token expiration setting
grep JWT_EXPIRE_MINUTES .env

# Increase if needed
nano .env
# Change: JWT_EXPIRE_MINUTES=60

# Restart API
docker compose restart minder-api
```

### Performance Issues

**Problem: Slow API response**

```bash
# Check response times
curl -w "@curl-format.txt" http://localhost:8000/health

# Check database query performance
docker exec postgres psql -U postgres -c "
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;
"

# Check memory usage
docker stats minder-api --no-stream

# Check CPU usage
docker exec minder-api top -b -n 1 | head -20
```

**Problem: High memory usage**

```bash
# Check container memory
docker stats --no-stream | grep minder

# Check for memory leaks
docker logs minder-api | grep -i memory

# Restart container
docker compose restart minder-api

# If persistent, increase memory limit in docker-compose.yml
services:
  minder-api:
    deploy:
      resources:
        limits:
          memory: 2G
```

### Network Issues

**Problem: Cannot access API from external network**

```bash
# Check API is listening on correct interface
netstat -tulpn | grep 8000

# Check firewall rules
sudo ufw status
sudo iptables -L -n

# Verify ALLOWED_ORIGINS
grep ALLOWED_ORIGINS .env

# Test from external machine
curl http://<server-ip>:8000/health
```

**Problem: Plugin cannot reach external APIs**

```bash
# Test DNS resolution
docker exec minder-api nslookup api.tefas.org.tr

# Test connectivity
docker exec minder-api curl -I https://api.tefas.org.tr

# Check proxy settings
docker exec minder-api env | grep -i proxy

# Verify network mode
docker network inspect minder_default
```

---

## Maintenance Tasks

### Daily Tasks
- Check container health: `docker ps`
- Review error logs: `docker logs minder-api 2>&1 | grep ERROR`
- Verify backups completed: `ls -lh /backup/minder/ | tail -5`

### Weekly Tasks
- Review disk space: `df -h`
- Check plugin data freshness
- Review Grafana dashboards
- Test backup restoration in staging

### Monthly Tasks
- Rotate secrets (JWT, database passwords)
- Update Docker images: `docker compose pull`
- Review and update documentation
- Security audit: check for vulnerabilities

---

## Emergency Procedures

### Complete System Restart

```bash
# Stop all services
docker compose down

# Verify all containers stopped
docker ps

# Start all services
docker compose up -d

# Verify health
curl http://localhost:8000/health
docker ps --format "table {{.Names}}\t{{.Status}}"
```

### Emergency Rollback

```bash
# Stop current deployment
docker compose down

# Restore previous backup
./scripts/restore.sh <previous-backup-id>

# Verify system health
curl http://localhost:8000/health
```

### Data Recovery

```bash
# Identify issue
docker logs minder-api | tail -100

# Restore specific database if needed
docker exec postgres psql -U postgres < /backup/minder/<backup-id>/postgres_fundmind.sql.gz

# Or restore entire system
./scripts/restore.sh <backup-id>
```

---

## Support & Resources

### Documentation
- GitHub Repository: https://github.com/wish-maker/minder
- Plugin Development Guide: `/root/minder/docs/PLUGIN_DEVELOPMENT.md`
- API Documentation: http://localhost:8000/docs (Swagger UI)

### Logs Location
- Application logs: `/var/log/minder/`
- Docker logs: `docker logs <container-name>`
- Backup logs: `/var/log/minder-backup.log`

### Configuration Files
- Environment variables: `.env`
- Application config: `config.yaml`
- Docker configuration: `docker-compose.yml`

---

## Version: 2.0.0
Last Updated: 2026-04-16
