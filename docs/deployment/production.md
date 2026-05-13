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
# Minder Platform - Production Deployment Guide
**Version**: 1.0
**Target Environment**: Production
**Current Status**: Development Ready → Production Deployment Planning

---

## 🎯 Executive Summary

This guide provides a comprehensive roadmap for deploying the Minder AI Platform to production. The platform is currently **fully operational** in development mode with all critical services healthy and security features enabled.

**Production Readiness**: 85% - requires security hardening and operational procedures

---

## 📊 Pre-Deployment Assessment

### ✅ Production-Ready Components
- [x] Core Architecture: Microservices with Docker Compose
- [x] Security: Zero-Trust with Traefik + Authelia
- [x] Databases: PostgreSQL 17.4, Redis 7.2, Qdrant, Neo4j
- [x] AI Services: Ollama, RAG Pipeline, Fine-tuning
- [x] Monitoring: Prometheus, Grafana, InfluxDB, Telegraf
- [x] Message Broker: RabbitMQ with multi-tenant setup
- [x] Service Health: 97% (28/29 containers healthy)
- [x] Rolling Updates: Zero-downtime deployment capability

### ⚠️ Requires Production Hardening
- [ ] **Secrets Management**: Implement Docker Secrets
- [ ] **SSL Certificates**: Replace self-signed certificates
- [ ] **DNS Configuration**: Set up proper domain names
- [ ] **Backup Strategy**: Database and configuration backups
- [ ] **Monitoring Alerts**: External alerting (PagerDuty, Slack)
- [ ] **Resource Scaling**: Adjust limits for production load
- [ ] **High Availability**: Multi-instance deployment
- [ ] **Disaster Recovery**: Failover and recovery procedures

---

## 🚀 Deployment Strategy

### Option A: Single-Server Deployment (Current)
**Best For**: Small teams, development, testing
**Capacity**: ~100 concurrent users
**Cost**: Low (single server)
**Complexity**: Low

**Pros**:
- Simple deployment
- Easy maintenance
- Lower cost
- Faster troubleshooting

**Cons**:
- Single point of failure
- Limited scalability
- No geographic redundancy

### Option B: High-Availability Deployment
**Best For**: Production, medium-to-large teams
**Capacity**: ~1000 concurrent users
**Cost**: Medium (3-5 servers)
**Complexity**: Medium

**Architecture**:
```
                    ┌─────────────────┐
                    │   Load Balancer │
                    │   (HAProxy/Nginx)│
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
       ┌──────▼──────┐ ┌────▼─────┐ ┌─────▼──────┐
       │  Server 1   │ │ Server 2 │ │  Server 3  │
       │  (Primary)  │ │(Standby) │ │ (Services) │
       │             │ │          │ │            │
       │ Traefik     │ │ Traefik  │ │ PostgreSQL │
       │ Authelia    │ │ Authelia │ │ Redis      │
       │ API Gateway │ │ API GW   │ │ RabbitMQ   │
       │ AI Services │ │ AI Svc   │ │ Qdrant     │
       └─────────────┘ └──────────┘ └────────────┘
```

**Pros**:
- High availability
- Load distribution
- Geographic redundancy possible
- Better fault tolerance

**Cons**:
- Higher cost
- More complex setup
- Requires synchronization

### Option C: Cloud-Native Deployment (Future)
**Best For**: Large scale, enterprise
**Capacity**: 10,000+ concurrent users
**Cost**: High (cloud infrastructure)
**Complexity**: High

**Technologies**:
- Kubernetes orchestration
- Cloud load balancers
- Managed databases
- Auto-scaling
- Multi-region deployment

---

## 🔐 Production Security Checklist

### Phase 1: Identity and Access Management

#### 1.1 Strong Authentication
- [ ] Generate production-grade secrets
  ```bash
  .setup/scripts/generate-secrets.sh
  ```
- [ ] Use password manager for admin credentials
- [ ] Enable MFA for all admin accounts
- [ ] Implement role-based access control (RBAC)

#### 1.2 SSL/TLS Certificates
- [ ] Obtain valid SSL certificates for:
  - `*.minder.local` domain
  - `api.minder.local`
  - `grafana.minder.local`
  - `auth.minder.local`
- [ ] Configure certificate auto-renewal (Let's Encrypt)
- [ ] Test SSL configuration: https://www.ssllabs.com/ssltest/
- [ ] Enable HSTS (HTTP Strict Transport Security)

#### 1.3 Network Security
- [ ] Configure firewall rules (only necessary ports)
- [ ] Set up VPN for admin access
- [ ] Implement IP whitelisting for sensitive services
- [ ] Configure DDoS protection
- [ ] Enable fail2ban for repeated failed logins

### Phase 2: Data Protection

#### 2.1 Database Security
- [ ] Enable PostgreSQL SSL connections
- [ ] Implement database user restrictions
- [ ] Configure database backups (daily, encrypted)
- [ ] Test database restore procedures
- [ ] Implement data retention policies

#### 2.2 Secrets Management
- [ ] Implement Docker Secrets (see DOCKER-SECRETS-IMPLEMENTATION-PLAN.md)
- [ ] Set up secret rotation schedule
- [ ] Encrypt secrets at rest
- [ ] Audit secret access logs

#### 2.3 Application Security
- [ ] Enable security headers in Traefik
- [ ] Configure rate limiting per service
- [ ] Implement request size limits
- [ ] Enable CORS for specific domains only
- [ ] Regular security updates

---

## 💾 Backup and Recovery Strategy

### Backup Components

#### 1. Database Backups
**PostgreSQL**:
```bash
# Daily backup script
#!/bin/bash
BACKUP_DIR="/backups/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
docker exec minder-postgres pg_dump -U minder minder | gzip > "$BACKUP_DIR/minder_$DATE.sql.gz"

# Keep 7 days of daily backups
find "$BACKUP_DIR" -name "minder_*.sql.gz" -mtime +7 -delete
```

**InfluxDB**:
```bash
# Backup InfluxDB metadata and data
docker exec minder-influxdb influx backup /backup/influxdb_$(date +%Y%m%d)
```

**Neo4j**:
```bash
# Neo4j database backup
docker exec minder-neo4j neo4j-admin database dump --to-path=/backups/neo4j
```

#### 2. Configuration Backups
```bash
# Backup all configuration files
tar -czf config_backup_$(date +%Y%m%d).tar.gz \
  infrastructure/docker/ \
  infrastructure/docker/traefik/ \
  infrastructure/docker/authelia/ \
  .env
```

#### 3. Volume Backups
```bash
# Backup Docker volumes
docker run --rm -v minder_postgres_data:/data -v /backups:/backup \
  alpine tar -czf /backup/postgres_volume_$(date +%Y%m%d).tar.gz /data
```

### Backup Schedule
- **Daily**: Database backups (automated at 2:00 AM)
- **Weekly**: Configuration backups
- **Monthly**: Full system backup (volumes + configs)
- **Immediate**: Before any major changes

### Recovery Procedures

#### Database Recovery
```bash
# Restore PostgreSQL
gunzip -c minder_20260505_020000.sql.gz | docker exec -i minder-postgres psql -U minder minder

# Restore InfluxDB
docker exec minder-influxdb influx restore /backup/influxdb_20260505

# Restore Neo4j
docker exec minder-neo4j neo4j-admin database load --from-path=/backups/neo4j
```

#### System Recovery
```bash
# Full system restore
1. Stop all services: ./setup.sh stop
2. Restore volumes from backup
3. Restore configuration files
4. Start services: ./setup.sh start
5. Verify health: ./setup.sh status
```

---

## 📈 Monitoring and Alerting

### Production Monitoring Stack

#### 1. Metrics Collection
**Current**: ✅ Operational
- Prometheus: Metrics storage
- Grafana: Visualization dashboards
- Telegraf: Metrics collection
- Node Exporter: Host metrics
- cAdvisor: Container metrics

**Production Enhancements**:
- [ ] Configure alerting rules
- [ ] Set up long-term metrics retention
- [ ] Implement custom business metrics
- [ ] Configure metrics aggregation

#### 2. Logging
**Current**: Basic container logs
**Production Enhancements**:
- [ ] Centralized logging (ELK/Loki)
- [ ] Log retention policies
- [ ] Structured logging format
- [ ] Log analysis and alerting

#### 3. Uptime Monitoring
**Recommended Tools**:
- UptimeRobot (external monitoring)
- Pingdom (synthetic monitoring)
- Statuspage (public status page)

### Alert Configuration

#### Critical Alerts (Immediate)
- Service down (health check failed)
- Database connection lost
- Authentication failure (Authelia down)
- Disk space > 80%
- Memory usage > 90%
- API error rate > 5%

#### Warning Alerts (Within 1 hour)
- High CPU usage (> 80% sustained)
- Memory usage > 75%
- Disk space > 70%
- Backup failures
- SSL certificate expiring soon

#### Info Alerts (Daily digest)
- Service restarts
- Configuration changes
- Performance degradation
- Security events

### Alert Channels
- **Email**: On-call engineers
- **Slack**: Development team
- **PagerDuty**: Critical incidents
- **SMS**: Emergency only

---

## 🚦 Performance Optimization

### Resource Tuning

#### 1. Database Optimization
**PostgreSQL**:
```yaml
# docker-compose.yml overrides
services:
  postgres:
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 4G
        reservations:
          cpus: '1.0'
          memory: 2G
    environment:
      POSTGRES_SHARED_BUFFERS: 1GB
      POSTGRES_EFFECTIVE_CACHE_SIZE: 3GB
      POSTGRES_WORK_MEM: 16MB
      POSTGRES_MAINTENANCE_WORK_MEM: 512MB
```

**Redis**:
```yaml
services:
  redis:
    command: >
      redis-server
      --maxmemory 2gb
      --maxmemory-policy allkeys-lru
      --save 900 1
      --save 300 10
```

#### 2. Application Optimization
**API Gateway**:
```yaml
services:
  api-gateway:
    deploy:
      resources:
        limits:
          cpus: '1.0'
          memory: 2G
      replicas: 3  # High availability
    environment:
      WORKERS: 4
      LOG_LEVEL: WARNING  # Reduce logging in production
```

#### 3. Caching Strategy
- [ ] Configure Redis caching for API responses
- [ ] Implement CDN for static assets
- [ ] Enable HTTP caching headers
- [ ] Use application-level caching

### Load Testing

#### Test Scenarios
```bash
# 1. Baseline performance test
ab -n 1000 -c 10 https://api.minder.local/api/health

# 2. Load test API endpoints
ab -n 10000 -c 100 -p data.json -T application/json \
   https://api.minder.local/api/v1/plugins

# 3. Stress test
ab -n 50000 -c 500 https://api.minder.local/api/v1/rag/query
```

#### Performance Targets
- **API Response Time**: < 200ms (p95)
- **Authentication**: < 100ms (p95)
- **Database Queries**: < 50ms (p95)
- **Concurrent Users**: 100+ simultaneous
- **Uptime**: 99.9% (8.76 hours downtime/year)

---

## 🔄 Deployment Process

### Pre-Deployment Checklist

#### 1 Week Before
- [ ] Review this deployment guide
- [ ] Schedule deployment window
- [ ] Notify stakeholders
- [ ] Prepare rollback plan
- [ ] Test backup/restore procedures

#### 1 Day Before
- [ ] Generate production secrets
- [ ] Configure DNS records
- [ ] Obtain SSL certificates
- [ ] Set up monitoring and alerting
- [ ] Prepare deployment scripts

#### 1 Hour Before
- [ ] Final system backup
- [ ] Verify all services healthy
- [ ] Prepare team for deployment
- [ ] Set up communication channels

### Deployment Steps

#### Step 1: Preparation (15 minutes)
```bash
# 1. Create deployment branch
git checkout -b deployment/production

# 2. Update configuration
cp infrastructure/docker/.env.example infrastructure/docker/.env
# Edit .env with production values

# 3. Generate secrets
.setup/scripts/generate-secrets.sh

# 4. Verify configuration
docker compose config
```

#### Step 2: Deployment (30 minutes)
```bash
# 1. Stop development services
./setup.sh stop

# 2. Apply production configuration
# Update docker-compose.yml with production settings

# 3. Start production services
./setup.sh start

# 4. Verify health
./setup.sh status
```

#### Step 3: Validation (15 minutes)
```bash
# 1. Test authentication
curl -k -X POST https://auth.minder.local/api/firstuser

# 2. Test API access
curl -k https://api.minder.local/api/health

# 3. Test monitoring
curl http://localhost:9090/-/healthy
curl http://localhost:3000/api/health

# 4. Test AI services
docker exec minder-ollama ollama list
```

#### Step 4: Smoke Tests (30 minutes)
- [ ] User login flow
- [ ] Plugin installation
- [ ] AI chat functionality
- [ ] RAG query execution
- [ ] Dashboard access
- [ ] Metrics visualization

### Post-Deployment

#### Immediate (First Hour)
- [ ] Monitor system metrics
- [ ] Check error logs
- [ ] Verify all services healthy
- [ ] Test critical user flows

#### First Day
- [ ] Monitor performance metrics
- [ ] Address any issues
- [ ] Fine-tune configurations
- [ ] Document any changes

#### First Week
- [ ] Analyze performance data
- [ ] Optimize based on usage patterns
- [ ] Update documentation
- [ ] Train support team

---

## 🆘 Troubleshooting Guide

### Common Production Issues

#### 1. Service Won't Start
**Symptoms**: Container exits immediately
**Diagnosis**:
```bash
docker logs <service-name>
docker inspect <service-name>
```
**Solutions**:
- Check configuration syntax
- Verify secret files exist
- Check resource availability
- Review dependency health

#### 2. High Memory Usage
**Symptoms**: OOM kills, slow performance
**Diagnosis**:
```bash
docker stats
free -h
```
**Solutions**:
- Increase memory limits
- Optimize application settings
- Restart services
- Scale horizontally

#### 3. Database Connection Issues
**Symptoms**: Connection timeouts, pool exhaustion
**Diagnosis**:
```bash
docker exec minder-postgres psql -U minder -c "SELECT count(*) FROM pg_stat_activity;"
```
**Solutions**:
- Increase connection pool size
- Check for connection leaks
- Optimize queries
- Add read replicas

#### 4. Authentication Failures
**Symptoms**: Users can't log in
**Diagnosis**:
```bash
docker logs minder-authelia
docker logs minder-traefik
```
**Solutions**:
- Verify Authelia database connectivity
- Check Redis for session storage
- Review user configuration
- Test authentication flow

---

## 📊 Maintenance Procedures

### Daily Tasks
- [ ] Check system status: `./setup.sh status`
- [ ] Review error logs
- [ ] Verify backup completion
- [ ] Monitor resource usage

### Weekly Tasks
- [ ] Review performance metrics
- [ ] Check disk space usage
- [ ] Test backup restore (random sample)
- [ ] Update security patches
- [ ] Review alert rules

### Monthly Tasks
- [ ] Security audit
- [ ] Performance optimization review
- [ ] Capacity planning
- [ ] Disaster recovery test
- [ ] Documentation update

### Quarterly Tasks
- [ ] Major version upgrades
- [ ] Architecture review
- [ ] Cost optimization
- [ ] Team training
- [ ] Security assessment

---

## 🎯 Success Metrics

### Technical KPIs
- **Uptime**: 99.9% target
- **Response Time**: < 200ms (p95)
- **Error Rate**: < 0.1%
- **Recovery Time**: < 1 hour
- **Deployment Time**: < 30 minutes

### Business KPIs
- **User Satisfaction**: > 4.5/5
- **Feature Adoption**: > 80%
- **Support Tickets**: < 10 per week
- **System Availability**: > 99.9%

---

## 📞 Support and Escalation

### Support Tiers

#### Tier 1: Basic Support (Development Team)
- **Scope**: Configuration, basic troubleshooting
- **Response Time**: 4 hours
- **Contact**: development-team@example.com

#### Tier 2: Advanced Support (DevOps Team)
- **Scope**: Performance issues, complex debugging
- **Response Time**: 1 hour
- **Contact**: devops-team@example.com

#### Tier 3: Emergency Support (On-Call)
- **Scope**: Critical outages, data loss
- **Response Time**: 15 minutes
- **Contact**: on-call@example.com

### Escalation Procedures
1. **Tier 1 Issue**: Attempt resolution for 30 minutes
2. **Escalate to Tier 2**: If not resolved or urgent
3. **Escalate to Tier 3**: If critical system impact
4. **Management Notification**: For major incidents

---

## 🏁 Conclusion

The Minder AI Platform is **ready for production deployment** with the following caveats:

**Must Complete Before Production**:
1. ✅ Implement Docker Secrets (5-7 hours)
2. ✅ Obtain SSL certificates (2-4 hours)
3. ✅ Configure DNS records (1-2 hours)
4. ✅ Set up backup procedures (2-3 hours)
5. ✅ Configure monitoring alerts (2-3 hours)

**Total Preparation Time**: 12-19 hours

**Recommendation**: Schedule a 1-week sprint to complete production preparation. The system architecture is solid, but security hardening and operational procedures need to be implemented before production use.

---

**Document Version**: 1.0
**Last Updated**: 2026-05-05 17:30:00
**Next Review**: After production deployment
**Maintainer**: Platform Operations Team
