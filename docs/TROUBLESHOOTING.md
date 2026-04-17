# Minder Troubleshooting Guide

## Table of Contents
1. [Quick Diagnostics](#quick-diagnostics)
2. [Container Issues](#container-issues)
3. [Database Problems](#database-problems)
4. [Plugin Failures](#plugin-failures)
5. [Authentication Issues](#authentication-issues)
6. [Performance Problems](#performance-problems)
7. [Network Connectivity](#network-connectivity)
8. [Data Collection Issues](#data-collection-issues)
9. [Monitoring Alerts](#monitoring-alerts)
10. [Emergency Procedures](#emergency-procedures)

---

## Quick Diagnostics

### Health Check Script

```bash
#!/bin/bash
# quick-diagnose.sh - Quick system health check

echo "=== Minder System Diagnostics ==="
echo ""

# 1. Container Status
echo "1. Container Status:"
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. API Health
echo -e "\n2. API Health:"
curl -sf http://localhost:8000/health | jq '.' || echo "❌ API not responding"

# 3. Plugin Status
echo -e "\n3. Plugin Status:"
curl -sf http://localhost:8000/plugins | jq '.plugins[] | {name, status, enabled}' || echo "❌ Cannot fetch plugin status"

# 4. Database Connectivity
echo -e "\n4. Database Connectivity:"
docker exec postgres pg_isready -U postgres && echo "✅ PostgreSQL ready" || echo "❌ PostgreSQL not ready"

# 5. Redis Connectivity
echo -e "\n5. Redis Connectivity:"
docker exec redis redis-cli ping && echo "✅ Redis ready" || echo "❌ Redis not ready"

# 6. Disk Space
echo -e "\n6. Disk Space:"
df -h | grep -E "(/$|/var)"

# 7. Memory Usage
echo -e "\n7. Memory Usage:"
free -h

# 8. Recent Errors
echo -e "\n8. Recent Errors (last 10):"
docker logs minder-api 2>&1 | grep -i error | tail -10

echo -e "\n=== Diagnostics Complete ==="
```

### Common Error Patterns

| Symptom | Likely Cause | Quick Fix |
|---------|-------------|-----------|
| Container unhealthy | Health check failing | Check `/health` endpoint |
| 0 records collected | API connectivity issue | Test API endpoint manually |
| High memory usage | Memory leak or insufficient limits | Restart container, increase limits |
| Slow API response | Database slow or blocked queries | Check DB performance, restart if needed |
| Authentication failed | Invalid token or expired credentials | Re-login, check JWT expiration |

---

## Container Issues

### Container Won't Start

**Symptoms:**
- Container exits immediately after start
- `docker ps` shows container not running
- Logs show initialization errors

**Diagnosis:**
```bash
# Check container logs
docker logs minder-api
docker logs postgres
docker logs redis

# Check for port conflicts
netstat -tulpn | grep -E ':(8000|5432|6379)'

# Check Docker daemon
docker ps -a
```

**Solutions:**

1. **Port Conflict**
   ```bash
   # Find conflicting process
   sudo lsof -i :8000
   
   # Kill conflicting process
   sudo kill -9 <PID>
   
   # Restart container
   docker compose up -d
   ```

2. **Volume Mount Issue**
   ```bash
   # Check volume mounts
   docker volume ls
   
   # Remove and recreate volumes
   docker compose down -v
   docker compose up -d
   ```

3. **Configuration Error**
   ```bash
   # Validate configuration
   docker config inspect minder_config
   
   # Rebuild container
   docker compose down
   docker compose build --no-cache
   docker compose up -d
   ```

### Container Unhealthy

**Symptoms:**
- `docker ps` shows "(unhealthy)" status
- Health check failing intermittently
- Container running but not responding

**Diagnosis:**
```bash
# Check health status
docker ps --format "table {{.Names}}\t{{.Status}}"

# Inspect health check
docker inspect minder-api | jq '.[0].State.Health'

# Test health endpoint manually
curl -v http://localhost:8000/health

# Check kernel initialization
docker logs minder-api | grep -E "(error|ERROR|failed|kernel)"
```

**Solutions:**

1. **Kernel Not Initialized**
   ```bash
   # Check kernel logs
   docker logs minder-api | grep -i kernel
   
   # Restart API container
   docker compose restart minder-api
   
   # Wait for startup (30 seconds)
   sleep 30
   curl http://localhost:8000/health
   ```

2. **Database Connection Failed**
   ```bash
   # Test database connectivity
   docker exec postgres pg_isready
   
   # Check network
   docker network inspect minder_default
   
   # Restart both containers
   docker compose restart postgres minder-api
   ```

3. **Memory Pressure**
   ```bash
   # Check memory usage
   docker stats minder-api --no-stream
   
   # Increase memory limit in docker-compose.yml
   # services:
   #   minder-api:
   #     deploy:
   #       resources:
   #         limits:
   #           memory: 2G
   ```

### Container Restart Loop

**Symptoms:**
- Container constantly restarting
- Logs show startup failures
- Container exits with error code

**Diagnosis:**
```bash
# Check restart count
docker ps -a --format "table {{.Names}}\t{{.Status}}"

# View last 50 lines of logs
docker logs --tail 50 minder-api

# Check exit code
docker inspect minder-api | jq '.[0].State.ExitCode'
```

**Solutions:**

1. **Configuration Error**
   ```bash
   # Validate .env file
   cat .env | grep -v "^#" | grep -v "^$"
   
   # Check for missing required variables
   grep -E "POSTGRES_PASSWORD|JWT_SECRET_KEY" .env
   
   # Fix and restart
   nano .env
   docker compose down
   docker compose up -d
   ```

2. **Dependency Not Ready**
   ```bash
   # Check dependent containers
   docker ps
   
   # Start dependencies first
   docker compose up -d postgres redis influxdb qdrant
   
   # Wait for databases to be ready
   sleep 15
   
   # Start API
   docker compose up -d minder-api
   ```

3. **Permission Issues**
   ```bash
   # Check file permissions
   ls -la /root/minder/
   
   # Fix permissions
   sudo chown -R $USER:$USER /root/minder/
   
   # Restart container
   docker compose restart minder-api
   ```

---

## Database Problems

### PostgreSQL Connection Failed

**Symptoms:**
- API cannot connect to database
- "Connection refused" errors
- Authentication failures

**Diagnosis:**
```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test PostgreSQL readiness
docker exec postgres pg_isready

# Check PostgreSQL logs
docker logs postgres | tail -50

# Test connection from API container
docker exec minder-api ping -c 2 postgres

# Verify credentials
docker exec postgres psql -U postgres -c "SELECT version();"
```

**Solutions:**

1. **Wrong Password**
   ```bash
   # Check .env file
   grep POSTGRES_PASSWORD .env
   
   # Update password in .env
   nano .env
   # POSTGRES_PASSWORD=<correct-password>
   
   # Restart both containers
   docker compose restart postgres minder-api
   ```

2. **Database Not Ready**
   ```bash
   # Wait for PostgreSQL to fully start
   docker exec postgres pg_isready -U postgres -t 5
   
   # Check if database exists
   docker exec postgres psql -U postgres -l
   
   # Create database if missing
   docker exec postgres psql -U postgres -c "CREATE DATABASE fundmind;"
   ```

3. **Network Issue**
   ```bash
   # Check Docker network
   docker network inspect minder_default
   
   # Verify both containers on same network
   docker inspect postgres | jq '.[0].NetworkSettings.Networks'
   docker inspect minder-api | jq '.[0].NetworkSettings.Networks'
   
   # Recreate network
   docker compose down
   docker network prune
   docker compose up -d
   ```

### Database Locked

**Symptoms:**
- Queries hanging
- "Database is locked" errors
- Slow response times

**Diagnosis:**
```bash
# Check active connections
docker exec postgres psql -U postgres -c "
SELECT pid, usename, application_name, state, query 
FROM pg_stat_activity 
WHERE datname = 'fundmind' 
ORDER BY state_change;
"

# Check for long-running queries
docker exec postgres psql -U postgres -c "
SELECT pid, now() - pg_stat_activity.query_start AS duration, query
FROM pg_stat_activity
WHERE state = 'active'
ORDER BY duration DESC;
"

# Check table locks
docker exec postgres psql -U postgres fundmind -c "
SELECT relname, mode, pid
FROM pg_locks l
JOIN pg_class c ON l.relation = c.oid
WHERE NOT granted;
"
```

**Solutions:**

1. **Terminate Long-Running Queries**
   ```bash
   # Find long-running query PID
   docker exec postgres psql -U postgres -c "
   SELECT pid, query 
   FROM pg_stat_activity 
   WHERE state = 'active' 
   AND now() - query_start > interval '5 minutes';
   "
   
   # Terminate specific query
   docker exec postgres psql -U postgres -c "
   SELECT pg_terminate_backend(<PID>);
   "
   ```

2. **Kill Idle Connections**
   ```bash
   # Find idle connections
   docker exec postgres psql -U postgres -c "
   SELECT pid, usename 
   FROM pg_stat_activity 
   WHERE state = 'idle' 
   AND state_change < now() - interval '10 minutes';
   "
   
   # Terminate idle connections
   docker exec postgres psql -U postgres -c "
   SELECT pg_terminate_backend(pid) 
   FROM pg_stat_activity 
   WHERE state = 'idle' 
   AND state_change < now() - interval '10 minutes';
   "
   ```

3. **Restart PostgreSQL**
   ```bash
   # Graceful restart
   docker compose restart postgres
   
   # Force restart (last resort)
   docker compose stop postgres
   docker compose start postgres
   
   # Wait for recovery
   docker exec postgres pg_isready -U postgres -t 30
   ```

### Disk Space Full

**Symptoms:**
- "No space left on device" errors
- Cannot write to database
- Database operations failing

**Diagnosis:**
```bash
# Check disk space
df -h

# Check database size
docker exec postgres psql -U postgres -c "
SELECT pg_database.datname, 
       pg_size_pretty(pg_database_size(pg_database.datname)) AS size
FROM pg_database
ORDER BY pg_database_size(pg_database.datname) DESC;
"

# Find large tables
docker exec postgres psql -U postgres fundmind -c "
SELECT schemaname, tablename,
       pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
"
```

**Solutions:**

1. **Vacuum Database**
   ```bash
   # Run VACUUM to reclaim space
   docker exec postgres psql -U postgres -c "VACUUM FULL;"
   
   # Analyze tables
   docker exec postgres psql -U postgres -c "VACUUM ANALYZE;"
   ```

2. **Clean Old Data**
   ```bash
   # Delete old records (adjust as needed)
   docker exec postgres psql -U postgres fundmind -c "
   DELETE FROM data_records 
   WHERE created_at < now() - interval '90 days';
   "
   
   # Vacuum after deletion
   docker exec postgres psql -U postgres fundmind -c "VACUUM FULL;"
   ```

3. **Clean Docker Resources**
   ```bash
   # Remove unused containers
   docker container prune -f
   
   # Remove unused images
   docker image prune -a -f
   
   # Remove unused volumes (BE CAREFUL!)
   docker volume prune -f
   ```

---

## Plugin Failures

### Plugin Not Loading

**Symptoms:**
- Plugin not listed in `/plugins` endpoint
- "Module not found" errors
- Plugin status shows "disabled"

**Diagnosis:**
```bash
# Check plugin directory exists
ls -la /root/minder/plugins/

# Check for Python syntax errors
docker exec minder-api python -m py_compile plugins/news/*.py

# Check plugin logs
docker logs minder-api | grep -i plugin

# Verify plugin configuration
cat /root/minder/config.yaml | grep -A 20 "plugins:"
```

**Solutions:**

1. **Fix Python Errors**
   ```bash
   # Check for syntax errors
   python3 -m py_compile plugins/news/news_module.py
   
   # Check imports
   docker exec minder-api python -c "
   from plugins.news.news_module import NewsModule
   print('Import successful')
   "
   ```

2. **Enable Plugin in Config**
   ```bash
   # Edit config.yaml
   nano /root/minder/config.yaml
   
   # Set enabled: true for plugin
   # plugins:
   #   news:
   #     enabled: true
   
   # Restart API
   docker compose restart minder-api
   ```

3. **Rebuild Container**
   ```bash
   # Rebuild with plugin changes
   docker compose down
   docker compose build --no-cache minder-api
   docker compose up -d
   ```

### Plugin Collecting Zero Records

**Symptoms:**
- Plugin shows "enabled" but 0 records collected
- API connectivity errors
- Data collection failures

**Diagnosis:**
```bash
# Check plugin status
curl -s http://localhost:8000/plugins | jq '.plugins[] | select(.name=="news")'

# Check plugin logs
docker logs minder-api | grep -i news | tail -20

# Test API connectivity manually
docker exec minder-api curl -I https://news.example.com

# Trigger manual collection
curl -X POST http://localhost:8000/plugins/news/collect \
  -H "Authorization: Bearer <token>"
```

**Solutions:**

1. **API Connectivity Issue**
   ```bash
   # Test from container
   docker exec minder-api curl -v https://api.example.com
   
   # Check DNS resolution
   docker exec minder-api nslookup api.example.com
   
   # Check firewall rules
   sudo ufw status
   sudo iptables -L -n
   ```

2. **API Key/Authentication**
   ```bash
   # Check API key in .env
   grep API_KEY .env
   
   # Test authentication
   docker exec minder-api curl -H "Authorization: Bearer $API_KEY" \
     https://api.example.com/test
   
   # Regenerate key if needed
   nano .env
   docker compose restart minder-api
   ```

3. **Rate Limiting**
   ```bash
   # Check for rate limit errors
   docker logs minder-api | grep -i "rate limit"
   
   # Reduce collection frequency
   nano /root/minder/config.yaml
   # collection_interval: 600  # 10 minutes instead of 5
   
   # Restart API
   docker compose restart minder-api
   ```

### Plugin Crashes

**Symptoms:**
- Plugin stops responding
- Unhandled exceptions in logs
- Plugin status shows "error"

**Diagnosis:**
```bash
# Check for exceptions
docker logs minder-api | grep -A 20 "Traceback"

# Check plugin logs specifically
docker logs minder-api | grep -i <plugin-name> | tail -50

# Test plugin in isolation
docker exec minder-api python -c "
from plugins.<plugin>.<plugin>_module import <Plugin>Module
plugin = <Plugin>Module({})
print(plugin.register())
"
```

**Solutions:**

1. **Fix Python Exception**
   ```bash
   # Identify error from logs
   docker logs minder-api | grep -B 5 -A 20 "Error"
   
   # Fix code
   nano /root/minder/plugins/<plugin>/<plugin>_module.py
   
   # Rebuild and restart
   docker compose down
   docker compose build --no-cache minder-api
   docker compose up -d
   ```

2. **Increase Timeout**
   ```bash
   # Edit plugin config
   nano /root/minder/plugins/<plugin>/config.yaml
   
   # Increase timeout
   # timeout: 60  # Increase from 30 to 60 seconds
   
   # Restart API
   docker compose restart minder-api
   ```

3. **Memory Issues**
   ```bash
   # Check memory usage
   docker stats minder-api --no-stream
   
   # Increase container memory
   nano docker-compose.yml
   # services:
   #   minder-api:
   #     deploy:
   #       resources:
   #         limits:
   #           memory: 2G
   
   # Restart with new limits
   docker compose down
   docker compose up -d
   ```

---

## Authentication Issues

### Cannot Login

**Symptoms:**
- Login returns 401 Unauthorized
- "Invalid credentials" error
- Token generation fails

**Diagnosis:**
```bash
# Verify auth manager initialized
docker logs minder-api | grep "Authentication manager"

# Check default user exists
docker exec minder-api python -c "
from api.auth import auth_manager
print('Users:', list(auth_manager.users.keys()))
"

# Test login manually
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

**Solutions:**

1. **Reset Admin Password**
   ```bash
   # Reset to default
   docker exec minder-api python -c "
from api.auth import auth_manager
import bcrypt
auth_manager.users['admin']['password_hash'] = bcrypt.hashpw('admin123'.encode(), bcrypt.gensalt()).decode()
print('Password reset to admin123')
"
   
   # Restart API
   docker compose restart minder-api
   ```

2. **Create New Admin User**
   ```bash
   # Create new user
   docker exec minder-api python -c "
from api.auth import auth_manager
auth_manager.create_user('newadmin', 'securepassword123', 'admin')
print('User created')
"
   
   # Test new user login
   curl -X POST http://localhost:8000/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "newadmin", "password": "securepassword123"}'
   ```

3. **Check JWT Configuration**
   ```bash
   # Verify JWT secret is set
   grep JWT_SECRET_KEY .env
   
   # Regenerate if missing
   openssl rand -hex 32 >> .env
   # Add as: JWT_SECRET_KEY=<generated-value>
   
   # Restart API
   docker compose restart minder-api
   ```

### Token Expired

**Symptoms:**
- 401 Unauthorized after using token
- "Token expired" error
- Frequent re-authentication required

**Diagnosis:**
```bash
# Check token expiration setting
grep JWT_EXPIRE_MINUTES .env

# Decode token (use jwt.io or jwt-cli)
echo "<your-token>" | jwt decode

# Check current time vs token expiration
date
```

**Solutions:**

1. **Increase Token Expiration**
   ```bash
   # Edit .env file
   nano .env
   # JWT_EXPIRE_MINUTES=60  # Increase from 30 to 60 minutes
   
   # Restart API
   docker compose restart minder-api
   ```

2. **Implement Refresh Tokens**
   ```bash
   # (Future enhancement - add refresh token mechanism)
   # For now, just re-login when token expires
   ```

3. **Use Persistent Session**
   ```bash
   # Store token securely and reuse
   # Example in Python:
   # import requests
   # token = response.json()['access_token']
   # headers = {'Authorization': f'Bearer {token}'}
   # future_requests = requests.get(url, headers=headers)
   ```

---

## Performance Problems

### Slow API Response

**Symptoms:**
- API requests take >1 second
- Timeouts on complex queries
- High response times

**Diagnosis:**
```bash
# Measure response time
time curl http://localhost:8000/health

# Check database query performance
docker exec postgres psql -U postgres -c "
SELECT query, mean_exec_time, calls 
FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;
"

# Check container resource usage
docker stats --no-stream | grep minder

# Profile API endpoint
docker exec minder-api python -m cProfile -s cumtime \
  -c "import requests; requests.get('http://localhost:8000/plugins')"
```

**Solutions:**

1. **Database Query Optimization**
   ```bash
   # Add indexes to slow tables
   docker exec postgres psql -U postgres fundmind -c "
   CREATE INDEX IF NOT EXISTS idx_created_at 
   ON data_records(created_at DESC);
   "
   
   # Analyze query plan
   docker exec postgres psql -U postgres fundmind -c "
   EXPLAIN ANALYZE SELECT * FROM data_records 
   WHERE created_at > NOW() - INTERVAL '7 days';
   "
   ```

2. **Enable Caching**
   ```bash
   # Check Redis is running
   docker exec redis redis-cli ping
   
   # Enable caching in config
   nano /root/minder/config.yaml
   # cache:
   #   enabled: true
   #   backend: redis
   #   ttl: 300
   
   # Restart API
   docker compose restart minder-api
   ```

3. **Increase Resources**
   ```bash
   # Increase CPU/memory limits
   nano docker-compose.yml
   # services:
   #   minder-api:
   #     deploy:
   #       resources:
   #         limits:
   #           cpus: '2'
   #           memory: 2G
   
   # Restart with new limits
   docker compose down
   docker compose up -d
   ```

### High Memory Usage

**Symptoms:**
- Container using >80% memory
- OOM (Out of Memory) kills
- System swapping

**Diagnosis:**
```bash
# Check memory usage
docker stats minder-api --no-stream

# Check for memory leaks
docker logs minder-api | grep -i memory

# Monitor over time
watch -n 5 'docker stats minder-api --no-stream'

# Check Python memory usage
docker exec minder-api python -c "
import psutil
process = psutil.Process()
print(f'Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB')
"
```

**Solutions:**

1. **Restart Container**
   ```bash
   # Quick fix - release memory
   docker compose restart minder-api
   
   # Monitor after restart
   docker stats minder-api
   ```

2. **Increase Memory Limit**
   ```bash
   # Edit docker-compose.yml
   nano docker-compose.yml
   # services:
   #   minder-api:
   #     deploy:
   #       resources:
   #         limits:
   #           memory: 2G  # Increase from 1G
   
   # Recreate container
   docker compose down
   docker compose up -d
   ```

3. **Investigate Memory Leak**
   ```bash
   # Profile memory usage
   docker exec minder-api python -c "
import tracemalloc
tracemalloc.start()
# ... run code ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
for stat in top_stats[:10]:
    print(stat)
"
   ```

---

## Network Connectivity

### Cannot Access API Externally

**Symptoms:**
- API works on localhost but not from external IP
- Connection refused from other machines
- Firewall blocking access

**Diagnosis:**
```bash
# Check what interface API is listening on
netstat -tulpn | grep 8000

# Check firewall rules
sudo ufw status
sudo iptables -L -n | grep 8000

# Test from local machine
curl http://localhost:8000/health

# Test from external machine
curl http://<server-ip>:8000/health
```

**Solutions:**

1. **Bind to All Interfaces**
   ```bash
   # Check .env file
   grep API_HOST .env
   
   # Should be: API_HOST=0.0.0.0 (not 127.0.0.1)
   nano .env
   # API_HOST=0.0.0.0
   
   # Restart API
   docker compose restart minder-api
   ```

2. **Configure Firewall**
   ```bash
   # Allow port 8000
   sudo ufw allow 8000/tcp
   
   # Or with iptables
   sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
   
   # Verify
   sudo ufw status
   ```

3. **Configure Docker Ports**
   ```bash
   # Check docker-compose.yml port mapping
   grep -A 5 "minder-api:" docker-compose.yml | grep ports
   
   # Should be: "8000:8000"
   nano docker-compose.yml
   # ports:
   #   - "8000:8000"
   
   # Restart
   docker compose down
   docker compose up -d
   ```

### Plugin Cannot Reach External APIs

**Symptoms:**
- Plugin collects 0 records
- "Connection timeout" errors
- DNS resolution failures

**Diagnosis:**
```bash
# Test DNS from container
docker exec minder-api nslookup api.example.com

# Test connectivity
docker exec minder-api curl -I https://api.example.com

# Check proxy settings
docker exec minder-api env | grep -i proxy

# Check network mode
docker network inspect minder_default
```

**Solutions:**

1. **Fix DNS Resolution**
   ```bash
   # Configure DNS in docker-compose.yml
   nano docker-compose.yml
   # services:
   #   minder-api:
   #     dns:
   #       - 8.8.8.8
   #       - 8.8.4.4
   
   # Restart
   docker compose restart minder-api
   ```

2. **Configure Proxy**
   ```bash
   # Add proxy settings to .env
   nano .env
   # HTTP_PROXY=http://proxy.example.com:8080
   # HTTPS_PROXY=http://proxy.example.com:8080
   # NO_PROXY=localhost,127.0.0.1,postgres,redis
   
   # Restart
   docker compose restart minder-api
   ```

3. **Check Network Policies**
   ```bash
   # Verify container can reach internet
   docker exec minder-api ping -c 3 8.8.8.8
   
   # Check if specific API blocked
   docker exec minder-api curl -v https://api.example.com
   
   # Allow in firewall if needed
   sudo ufw allow out 443/tcp
   ```

---

## Monitoring Alerts

### High Error Rate

**Symptoms:**
- Grafana shows >5% error rate
- Alertmanager firing alerts
- Many 500 errors in logs

**Diagnosis:**
```bash
# Check recent errors
docker logs minder-api --since 1h | grep -i error | tail -50

# Check error rate metrics
curl http://localhost:8000/metrics | grep error

# Check specific endpoint errors
docker logs minder-api | grep "POST /chat" | grep "500"
```

**Solutions:**

1. **Identify Failing Component**
   ```bash
   # Check which plugin failing
   curl -s http://localhost:8000/plugins | jq '.plugins[] | select(.status != "ready")'
   
   # Check database errors
   docker logs postgres | grep -i error
   
   # Check Redis errors
   docker logs redis | grep -i error
   ```

2. **Fix Root Cause**
   ```bash
   # Based on error type:
   # - API connectivity: See Network Connectivity section
   # - Database issues: See Database Problems section
   # - Plugin issues: See Plugin Failures section
   ```

3. **Disable Failing Plugin**
   ```bash
   # Temporarily disable problematic plugin
   nano /root/minder/config.yaml
   # plugins:
   #   problematic_plugin:
   #     enabled: false
   
   # Restart API
   docker compose restart minder-api
   ```

### Disk Space Alert

**Symptoms:**
- Disk usage >80%
- Cannot write backups
- Database operations failing

**Diagnosis:**
```bash
# Check disk space
df -h

# Find large files
du -sh /var/lib/docker/* | sort -h

# Check database size
docker exec postgres psql -U postgres -c "
SELECT pg_size_pretty(pg_database_size('fundmind'));
"
```

**Solutions:**

1. **Clean Docker Resources**
   ```bash
   # Remove unused containers
   docker container prune -f
   
   # Remove unused images
   docker image prune -a -f
   
   # Remove old logs
   truncate -s 0 /var/log/minder/*.log
   ```

2. **Archive Old Data**
   ```bash
   # Backup old data
   ./scripts/backup.sh
   
   # Delete old records from database
   docker exec postgres psql -U postgres fundmind -c "
   DELETE FROM data_records 
   WHERE created_at < NOW() - INTERVAL '90 days';
   "
   
   # Vacuum database
   docker exec postgres psql -U postgres -c "VACUUM FULL;"
   ```

3. **Expand Disk**
   ```bash
   # (Requires OS-level changes)
   # Add new disk, expand volume, etc.
   ```

---

## Emergency Procedures

### Complete System Failure

**Symptoms:**
- All containers down
- No API response
- System completely unresponsive

**Recovery Steps:**

1. **Assess Damage**
   ```bash
   # Check container status
   docker ps -a
   
   # Check logs
   docker logs --tail 100 minder-api
   docker logs --tail 100 postgres
   
   # Check system resources
   df -h
   free -h
   ```

2. **Restart All Services**
   ```bash
   # Stop everything
   docker compose down
   
   # Wait 10 seconds
   sleep 10
   
   # Start all services
   docker compose up -d
   
   # Verify health
   sleep 30
   curl http://localhost:8000/health
   ```

3. **If Restart Fails, Restore Backup**
   ```bash
   # Find latest backup
   ls -lt /backup/minder/ | head -5
   
   # Restore from backup
   ./scripts/restore.sh latest
   ```

### Data Corruption

**Symptoms:**
- Database queries return errors
- Inconsistent data
- Plugin data not updating

**Recovery Steps:**

1. **Identify Corrupted Data**
   ```bash
   # Check database integrity
   docker exec postgres psql -U postgres -c "
   SELECT schemaname, tablename, n_live_tup, n_dead_tup
   FROM pg_stat_user_tables
   ORDER BY n_dead_tup DESC;
   "
   ```

2. **Restore from Backup**
   ```bash
   # Stop API to prevent writes
   docker compose stop minder-api
   
   # Restore database
   ./scripts/restore.sh <backup-id>
   
   # Start API
   docker compose start minder-api
   ```

3. **Verify Data Integrity**
   ```bash
   # Check record counts
   curl -s http://localhost:8000/plugins | jq '.plugins[] | {name: .name, records: .records_collected}'
   
   # Verify recent data exists
   docker exec postgres psql -U postgres fundmind -c "
   SELECT COUNT(*) FROM data_records 
   WHERE created_at > NOW() - INTERVAL '1 day';
   "
   ```

### Security Incident

**Symptoms:**
- Suspicious login attempts
- Unauthorized access
- Data exfiltration suspected

**Response Steps:**

1. **Contain Incident**
   ```bash
   # Stop all services
   docker compose down
   
   # Preserve evidence
   cp /var/log/minder/*.log /tmp/evidence/
   docker logs minder-api > /tmp/evidence/minder-api.log
   
   # Change all secrets
   openssl rand -hex 32 > /tmp/new_jwt_secret
   openssl rand -base64 24 > /tmp/new_db_password
   ```

2. **Investigate**
   ```bash
   # Check authentication logs
   grep "Authentication" /tmp/evidence/minder-api.log | tail -100
   
   # Check for failed login attempts
   grep "failed" /tmp/evidence/minder-api.log | tail -50
   
   # Check API access logs
   grep "POST\|GET\|DELETE" /tmp/evidence/minder-api.log | tail -100
   ```

3. **Recover**
   ```bash
   # Update .env with new secrets
   nano .env
   # Paste new secrets
   
   # Change admin passwords
   docker compose up -d postgres
   docker exec postgres psql -U postgres -c "
   ALTER USER postgres WITH PASSWORD '<new-password>';
   "
   
   # Start services
   docker compose up -d
   
   # Verify all users legitimate
   curl -s http://localhost:8000/auth/users \
     -H "Authorization: Bearer <admin-token>"
   ```

---

## Getting Help

### Collect Diagnostic Information

```bash
#!/bin/bash
# collect-diags.sh - Gather diagnostic info

OUTPUT_DIR="/tmp/minder-diags-$(date +%Y%m%d_%H%M%S)"
mkdir -p "$OUTPUT_DIR"

echo "Collecting diagnostics to $OUTPUT_DIR"

# Container status
docker ps -a > "$OUTPUT_DIR/containers.txt"

# Logs
docker logs minder-api --tail 500 > "$OUTPUT_DIR/minder-api.log"
docker logs postgres --tail 500 > "$OUTPUT_DIR/postgres.log"
docker logs redis --tail 500 > "$OUTPUT_DIR/redis.log"

# Configuration
cp .env "$OUTPUT_DIR/env.txt"
cp config.yaml "$OUTPUT_DIR/config.yaml"

# System info
df -h > "$OUTPUT_DIR/disk-space.txt"
free -h > "$OUTPUT_DIR/memory.txt"
uname -a > "$OUTPUT_DIR/system.txt"

# Network info
netstat -tulpn > "$OUTPUT_DIR/network.txt"

echo "Diagnostics collected. Create archive:"
echo "tar -czf minder-diags.tar.gz $OUTPUT_DIR"
```

### Contact Information

- **GitHub Issues**: https://github.com/wish-maker/minder/issues
- **Documentation**: http://localhost:8000/docs (when running)
- **Email**: noreply@github.com

---

## Version: 2.0.0
Last Updated: 2026-04-16
