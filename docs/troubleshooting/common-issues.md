# 🔧 Common Issues

Frequently encountered problems and their solutions.

---

## 🚦 Service Issues

### 1. Services Won't Start

**Problem:**
```
Container status: Exited (1)
Logs: "Connection refused" or "Port already in use"
```

**Solution:**
```bash
# Check port conflicts
sudo netstat -tulpn | grep -E "8000|8001|8004|8005|5432|6379|6333"

# Stop all services
docker compose down

# Start services again
docker compose up -d

# Check logs
docker compose logs
```

**Root Cause:**
- Port conflicts
- Previous containers not properly stopped
- Database connection issues

---

### 2. High Memory Usage

**Problem:**
```
Container status: Memory limit exceeded
Logs: "OOM killed"
```

**Solution:**
```bash
# Check memory usage
docker stats

# Restart services
docker compose restart

# Clear Redis cache
docker exec minder-redis redis-cli FLUSHALL

# Check service memory usage
docker stats --no-stream | grep minder
```

**Root Cause:**
- Too many containers running
- Inefficient memory usage
- Memory leaks in plugins

**Prevention:**
- Limit container memory in docker-compose.yml
- Clear caches regularly
- Monitor memory usage

---

### 3. Database Connection Issues

**Problem:**
```
Logs: "could not connect to server: Connection refused"
Logs: "FATAL: password authentication failed"
```

**Solution:**
```bash
# Check database status
docker logs minder-postgres --tail 50
docker logs minder-redis --tail 50

# Restart databases
docker compose restart postgres redis

# Check database connection
docker exec minder-postgres pg_isready
docker exec minder-redis redis-cli ping

# Test connection
docker exec -it minder-postgres psql -U minder -d minder -c "SELECT 1;"
```

**Root Cause:**
- Database container not running
- Incorrect credentials in .env file
- Network issues between containers

**Prevention:**
- Keep databases healthy
- Use environment variables for credentials
- Test connection regularly

---

### 4. Plugin Load Failures

**Problem:**
```
Plugin count: 3/5 (expected: 5/5)
Logs: "Failed to load plugin: [plugin_name]"
```

**Solution:**
```bash
# Check plugin directory
ls -la /root/minder/src/plugins/

# Check plugin configuration
cat /root/minder/src/plugins/*/plugin.yml

# Test plugin manually
cd /root/minder
python -c "
import sys
sys.path.insert(0, 'src')
from plugins.crypto import crypto_module
metadata = crypto_module.register()
print(f'Plugin registered: {metadata.name}')
"

# Rebuild plugin-registry
docker compose build plugin-registry
docker compose up -d plugin-registry
```

**Root Cause:**
- Plugin configuration errors
- Missing dependencies
- Import errors

**Prevention:**
- Follow plugin development guide
- Test plugins locally
- Keep dependencies updated

---

## 🌐 Network Issues

### 5. Container Networking Problems

**Problem:**
```
Logs: "Error connecting to host: [service-name]"
```

**Solution:**
```bash
# Check network configuration
docker network ls
docker network inspect minder_default

# Test connectivity
docker exec minder-api-gateway ping minder-postgres
docker exec minder-api-gateway ping minder-redis

# Restart network
docker network prune
docker compose up -d
```

**Root Cause:**
- Network configuration errors
- Container network not created
- DNS resolution issues

**Prevention:**
- Use docker-compose network naming
- Test connectivity regularly
- Use service names in configuration

---

## 🔒 Security Issues

### 6. Authentication Failures

**Problem:**
```
Logs: "Invalid JWT token"
Error: 401 Unauthorized
```

**Solution:**
```bash
# Get new token
curl -X POST http://localhost:8000/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your_password"}'

# Check JWT secret in .env
cat infrastructure/docker/.env | grep JWT_SECRET

# Restart API gateway to reload secret
docker compose restart api-gateway
```

**Root Cause:**
- Invalid or expired token
- Wrong credentials
- JWT secret mismatch

**Prevention:**
- Use secure passwords
- Implement token refresh
- Validate tokens properly

---

## 📊 Monitoring Issues

### 7. Metrics Not Appearing

**Problem:**
```
Prometheus: Target status shows "down"
Grafana: No data in panels
```

**Solution:**
```bash
# Check Prometheus target
curl http://localhost:9090/api/v1/targets

# Check metrics endpoint
curl http://localhost:8000/metrics

# Restart Prometheus
docker restart minder-prometheus

# Check network connectivity
docker exec minder-prometheus wget -qO- http://minder-api-gateway:8000/metrics
```

**Root Cause:**
- Prometheus not scraping correctly
- Metrics endpoint not accessible
- Network connectivity issues

**Prevention:**
- Monitor Prometheus targets
- Keep metrics endpoint healthy
- Test connectivity regularly

---

## 🗄️ Data Issues

### 8. Database Not Updating

**Problem:**
```
Database tables empty
Plugin data not being stored
```

**Solution:**
```bash
# Check database content
docker exec minder-postgres psql -U minder -d minder -c "SELECT count(*) FROM plugins;"

# Check plugin logs
docker logs minder-plugin-registry --tail 100 | grep ERROR

# Restart plugin-registry
docker compose restart plugin-registry

# Check database permissions
docker exec -it minder-postgres psql -U minder -d minder -c "\l"
```

**Root Cause:**
- Database connection issues
- Permission problems
- Plugin errors

**Prevention:**
- Regular database backups
- Monitor plugin logs
- Test data storage

---

## 📝 General Issues

### 9. Disk Space Issues

**Problem:**
```
Logs: "No space left on device"
Error: Container failed to start
```

**Solution:**
```bash
# Check disk usage
df -h

# Clean up Docker
docker system prune -a

# Remove old containers
docker compose down
docker container prune

# Clear logs
docker logs --tail 0 $(docker ps -aq) > /dev/null 2>&1
```

**Root Cause:**
- Too much disk usage
- Large Docker images
- Old logs

**Prevention:**
- Monitor disk usage
- Clean up regularly
- Use volume limits

---

### 10. Configuration Issues

**Problem:**
```
Services not using correct configuration
Environment variables not applied
```

**Solution:**
```bash
# Check environment variables
docker exec minder-api-gateway env | grep MINDER

# Check docker-compose.yml
cat infrastructure/docker/docker-compose.yml | grep -A 5 environment

# Restart services with new config
docker compose up -d --force-recreate
```

**Root Cause:**
- Wrong environment variables
- Configuration not loaded
- Cache issues

**Prevention:**
- Use .env files
- Document configuration
- Test configuration changes

---

## 🔍 Debugging Tips

### Enable Debug Logs

```bash
# Update .env file
LOG_LEVEL=DEBUG

# Restart services
docker compose down
docker compose up -d
```

### Check Container Health

```bash
# Check all containers
docker ps -a | grep minder

# Check specific container
docker inspect minder-api-gateway

# Check container logs
docker logs minder-api-gateway --tail 100
```

### Test Endpoints

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test API gateway
curl http://localhost:8001/v1/plugins

# Test specific plugin
curl http://localhost:8000/v1/plugins/crypto/collect
```

---

## 📚 Related Documentation

- **[Deployment Guide](../deployment/README.md)** - Deployment troubleshooting
- **[Troubleshooting Guide](../troubleshooting/README.md)** - Overview
- **[Known Issues](../references/ISSUES.md)** - Known problems
- **[API Reference](../api/README.md)** - API endpoint issues

---

## 🤝 Getting Help

If you encounter an issue not listed here:

1. Check [Known Issues](../references/ISSUES.md)
2. Search GitHub Issues
3. Create a new issue with:
   - Detailed error messages
   - Container logs
   - Configuration files
   - Steps to reproduce

---

**Last Updated:** 2026-04-19
