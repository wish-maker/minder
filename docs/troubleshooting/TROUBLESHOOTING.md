# 🔧 Troubleshooting Guide - Minder Platform

**Last Updated:** 2026-05-10
**Platform Version:** 1.0.0
**Status:** Production Ready (32 containers, 27 healthy)

---

## 📋 Table of Contents

1. [Common Issues](#common-issues)
2. [Authentication & Access](#authentication--access)
3. [Service Health](#service-health)
4. [Network Connectivity](#network-connectivity)
5. [Database Issues](#database-issues)
6. [Performance Issues](#performance-issues)
7. [Monitoring & Debugging](#monitoring--debugging)

---

## 🚨 Common Issues

### Issue 1: "404 Page Not Found" on All Services

**Symptom:** All HTTPS requests return "404 page not found"

**Root Cause:** Traefik routing configuration issues

**Solution:**
```bash
# Check Traefik logs
docker logs minder-traefik --tail 50

# Verify environment variables
cat infrastructure/docker/.env | grep TRAEFIK

# Restart Traefik
cd infrastructure/docker
docker compose restart traefik
```

**Prevention:** Ensure all middleware references use `@file` suffix in docker-compose.yml

---

### Issue 2: Services Not Responding on Ports 8000-8007

**Symptom:** HTTP requests to ports 8000-8007 timeout or return no response

**Root Cause:** Services are **intentionally not exposed** on host ports (security design)

**Solution:** Access services through Traefik reverse proxy:
```bash
# ❌ WRONG - Direct port access (blocked by design)
curl http://localhost:8000/health

# ✅ CORRECT - Through Traefik
curl -k https://api.minder.local/api/health

# ✅ CORRECT - Internal network access
curl http://172.19.0.14:8000/health
```

**Explanation:** This is **zero-trust architecture** - Pillar 1 security design

---

### Issue 3: "302 Found" Redirects to Authelia

**Symptom:** All requests redirect to `https://auth.minder.local/?rd=...`

**Root Cause:** This is **CORRECT BEHAVIOR** - zero-trust authentication working as designed

**Solution:**
```bash
# Step 1: Access Authelia and authenticate
curl -skL https://auth.minder.local/

# Step 2: Use authentication cookie for subsequent requests
curl -sk https://api.minder.local/api/health \
  -b "authelia_session=YOUR_SESSION_COOKIE"
```

**Verification:**
```bash
# Check authentication is working
curl -skI https://api.minder.local/api/health
# Should return: HTTP/2 302 (redirect to Authelia)
```

---

## 🔐 Authentication & Access

### How to Access Services

**Method 1: Through Authelia (Production Mode)**

1. Open browser: `https://auth.minder.local`
2. Login with credentials from `authelia/users_database.yml`
3. Access other services with active session

**Method 2: Direct Container Access (Development)**

```bash
# Shell access to any service
./setup.sh shell api-gateway

# Execute commands inside container
curl http://localhost:8000/health

# Via container IP from host
curl http://172.19.0.14:8000/health
```

**Method 3: Docker Exec (Debugging)**

```bash
# API Gateway
docker exec minder-api-gateway curl http://localhost:8000/health

# Plugin Registry
docker exec minder-plugin-registry curl http://localhost:8002/health

# RAG Pipeline
docker exec minder-rag-pipeline curl http://localhost:8003/health
```

---

## 🏥 Service Health

### Check Service Status

**All Services:**
```bash
./setup.sh status
```

**Specific Service:**
```bash
docker ps | grep api-gateway
docker logs minder-api-gateway --tail 50
```

**Health Endpoints:**
```bash
# API Gateway (internal network)
curl http://172.19.0.14:8000/health

# Plugin Registry
curl http://172.19.0.15:8002/health

# RAG Pipeline
curl http://172.19.0.16:8003/health
```

### Common Health Issues

**Issue: Container in "Restarting" loop**

```bash
# Check logs
docker logs minder-service-name --tail 100

# Common causes:
# 1. Configuration errors
# 2. Missing environment variables
# 3. Dependency not ready
# 4. Port conflicts

# Solution: Fix configuration, then recreate
cd infrastructure/docker
docker compose stop service-name
docker compose rm -f service-name
docker compose up -d service-name
```

**Issue: Service stuck in "Starting" state**

```bash
# Check if dependencies are ready
docker ps | grep postgres
docker ps | grep redis

# Increase health check timeout if needed
# Edit docker-compose.yml, adjust:
# healthcheck:
#   interval: 30s
#   timeout: 10s
#   start_period: 60s
```

---

## 🌐 Network Connectivity

### Verify Network Configuration

```bash
# Check network exists
docker network ls | grep docker_minder-network

# Inspect network
docker network inspect docker_minder-network

# Check container IPs
docker network inspect docker_minder-network | grep -A 3 "IPv4Address"
```

### Test Service Connectivity

**API Gateway to Dependencies:**
```bash
# From API Gateway container
docker exec minder-api-gateway curl http://minder-postgres:5432
docker exec minder-api-gateway curl http://minder-redis:6379
docker exec minder-api-gateway curl http://minder-qdrant:6333
```

**Service-to-Service:**
```bash
# Plugin Registry to API Gateway
docker exec minder-plugin-registry curl http://minder-api-gateway:8000/health

# RAG Pipeline to Qdrant
docker exec minder-rag-pipeline curl http://minder-qdrant:6333/collections
```

### DNS Resolution Issues

```bash
# Check if service names resolve
docker exec minder-api-gateway nslookup minder-postgres
docker exec minder-api-gateway nslookup minder-redis

# Test with ping
docker exec minder-api-gateway ping -c 2 minder-postgres
```

---

## 💾 Database Issues

### PostgreSQL

**Check Connection:**
```bash
docker exec minder-postgres psql -U minder -c "SELECT version();"
docker exec minder-postgres psql -U minder -c "\l"
```

**Common Issues:**

1. **Connection Refused:**
   ```bash
   # Check if PostgreSQL is ready
   docker exec minder-postgres pg_isready -U minder

   # Check logs
   docker logs minder-postgres --tail 50
   ```

2. **Database Not Found:**
   ```bash
   # List databases
   docker exec minder-postgres psql -U minder -c "\l"

   # Create database if missing
   docker exec minder-postgres psql -U minder -c "CREATE DATABASE minder;"
   ```

3. **Performance Issues:**
   ```bash
   # Check active connections
   docker exec minder-postgres psql -U minder -c "SELECT count(*) FROM pg_stat_activity;"

   # Check slow queries
   docker exec minder-postgres psql -U minder -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
   ```

### Redis

**Check Connection:**
```bash
docker exec minder-redis redis-cli -a YOUR_REDIS_PASSWORD ping
```

**Common Issues:**

1. **Authentication Failed:**
   ```bash
   # Check password in .env
   grep REDIS_PASSWORD infrastructure/docker/.env

   # Test with correct password
   docker exec minder-redis redis-cli -a ACTUAL_PASSWORD ping
   ```

2. **Memory Issues:**
   ```bash
   # Check memory usage
   docker exec minder-redis redis-cli -a PASSWORD INFO memory

   # Check max memory setting
   docker exec minder-redis redis-cli -a PASSWORD CONFIG GET maxmemory
   ```

### Neo4j

**Check Connection:**
```bash
# HTTP endpoint
curl http://172.19.0.12:7474

# Cypher endpoint
curl -X POST http://172.19.0.12:7474/db/neo4j/tx/commit \
  -H "Content-Type: application/json" \
  -d '{"statements":[{"statement":"RETURN 1"}]}'
```

**Common Issues:**

1. **Service Not Ready:**
   ```bash
   # Wait for Neo4j to fully start
   docker logs minder-neo4j --tail 50

   # Check if "Remote interface available" in logs
   docker logs minder-neo4j | grep "Remote interface available"
   ```

2. **Authentication Issues:**
   ```bash
   # Check password
   grep NEO4J_AUTH infrastructure/docker/.env

   # Test connection
   curl -u neo4j:PASSWORD http://172.19.0.12:7474
   ```

### Qdrant

**Check Connection:**
```bash
# Check collections
curl http://172.19.0.13:6333/collections

# Check cluster info
curl http://172.19.0.13:6333/cluster
```

**Common Issues:**

1. **No Collections Found:**
   ```bash
   # This is normal for fresh install
   # Collections are created dynamically by services

   # Verify Qdrant is responding
   curl http://172.19.0.13:6333/
   ```

2. **Storage Issues:**
   ```bash
   # Check storage status
   curl http://172.19.0.13:6333/telemetry

   # Check disk space
   df -h | grep qdrant
   ```

---

## ⚡ Performance Issues

### High Memory Usage

**Check Memory:**
```bash
# All containers
docker stats --no-stream

# Specific service
docker stats minder-api-gateway --no-stream
```

**Solutions:**
```bash
# 1. Restart memory-heavy services
./setup.sh restart api-gateway

# 2. Check for memory leaks
docker logs minder-service-name | grep -i "memory\|oom\|out of"

# 3. Adjust memory limits in docker-compose.yml
# deploy:
#   resources:
#     limits:
#       memory: 512M
```

### High CPU Usage

**Check CPU:**
```bash
docker stats --no-stream | sort -k 3 -h
```

**Solutions:**
```bash
# 1. Check what's consuming CPU
docker top minder-service-name

# 2. Check process count
docker exec minder-service-name ps aux

# 3. Scale horizontally if needed
docker compose up -d --scale api-gateway=3
```

### Slow Response Times

**Check Response Time:**
```bash
# API Gateway
time curl http://172.19.0.14:8000/health

# Database query time
docker exec minder-postgres psql -U minder -c "SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;"
```

**Solutions:**
```bash
# 1. Check network latency
docker exec minder-api-gateway ping -c 10 minder-postgres

# 2. Check database connection pool
docker logs minder-api-gateway | grep -i "connection\|pool"

# 3. Enable query caching in Redis
docker exec minder-redis redis-cli -a PASSWORD CONFIG SET maxmemory 256mb
docker exec minder-redis redis-cli -a PASSWORD CONFIG SET maxmemory-policy allkeys-lru
```

---

## 📊 Monitoring & Debugging

### View Logs

**All Services:**
```bash
./setup.sh logs
```

**Specific Service:**
```bash
./setup.sh logs api-gateway
docker logs minder-api-gateway --tail 100 -f
```

**Last 50 Lines:**
```bash
docker logs minder-api-gateway --tail 50
```

**Follow Logs:**
```bash
docker logs minder-api-gateway -f
```

### Check Metrics

**Prometheus:**
```bash
# Check targets
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check alerts
curl http://localhost:9090/api/v1/alerts | jq '.data.alerts[] | {alert: .labels.alertname, state: .state}'
```

**Grafana:**
```bash
# Check datasources
curl -u admin:admin http://localhost:3000/api/datasources | jq '.[] | {name: .name, type: .type}'

# Check dashboards
curl -u admin:admin http://localhost:3000/api/search | jq '.[] | {title: .title, uri: .uri}'
```

### Health Check Scripts

**Run All Health Checks:**
```bash
# Comprehensive service test
/tmp/comprehensive-service-test.sh

# Database connectivity
/tmp/database-connectivity-test.sh

# API integration
/tmp/api-integration-test.sh

# Monitoring stack
/tmp/monitoring-stack-test.sh

# Service dependencies
/tmp/service-dependencies-test.sh
```

---

## 🚨 Emergency Procedures

### Full System Restart

```bash
# Stop all services
./setup.sh stop

# Wait 10 seconds
sleep 10

# Start all services
./setup.sh start

# Monitor startup
./setup.sh status
```

### Restore from Backup

```bash
# List available backups
./setup.sh backup --list

# Restore specific backup
./setup.sh restore --backup=BACKUP_FILE

# Restore all databases
./setup.sh restore --all
```

### Emergency Access

**If Authelia is down:**
```bash
# Access services directly via internal network
docker exec minder-api-gateway curl http://localhost:8000/health

# Temporarily disable authentication (NOT RECOMMENDED)
# Edit traefik/dynamic/authelia-middleware.yml
# Set: forwardAuth: ""
# Then: docker compose restart traefik
```

**If Traefik is down:**
```bash
# Access services via container IPs
curl http://172.19.0.14:8000/health
curl http://172.19.0.15:8002/health
curl http://172.19.0.16:8003/health
```

---

## 📞 Getting Help

### Collect Diagnostic Information

```bash
# System status
./setup.sh status > /tmp/status.txt

# All logs
./setup.sh logs > /tmp/all-logs.txt 2>&1

# Container stats
docker stats --no-stream > /tmp/stats.txt

# Network info
docker network inspect docker_minder-network > /tmp/network.json

# Service health
/tmp/comprehensive-service-test.sh > /tmp/health-check.txt 2>&1
```

### Useful Commands

```bash
# Find problematic containers
docker ps -a | grep -v "healthy"

# Check for restart loops
docker ps -a | grep "Restarting"

# View resource usage
docker stats --no-stream | sort -k 3 -h

# Check disk space
df -h

# Check Docker disk usage
docker system df
```

---

## 📚 Additional Resources

- [Architecture Overview](../architecture/overview.md)
- [Security Architecture](../operations/security-architecture.md)
- [Service Access Guide](../operations/service-access.md)
- [Version Manifest](../VERSION_MANIFEST.md)
- [Setup.sh Documentation](../../setup.sh)

---

*Last Updated: 2026-05-10*
*Platform Version: 1.0.0*
*Status: Production Ready*
