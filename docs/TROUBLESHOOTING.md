# Minder Platform - Comprehensive Troubleshooting Guide

## 🚨 Quick Diagnostics

### Instant Health Check

```bash
# Run comprehensive health check
./scripts/health-check.sh

# Quick service status
./deploy.sh status

# Check specific service
docker ps | grep minder
```

---

## 🔧 Common Issues & Solutions

### 1. Services Won't Start

#### Symptoms
- Container exits immediately
- `docker ps` shows empty list
- Errors in logs

#### Diagnosis
```bash
# Check logs
./deploy.sh logs <service-name>

# Check container status
docker ps -a

# Check specific service logs
docker logs minder-<service-name>
```

#### Solutions

**A. Port Already in Use**
```bash
# Find what's using the port
sudo lsof -i :8000

# Kill the process
sudo kill -9 <PID>

# OR change port in .env
vim infrastructure/docker/.env
# Change PORT=8000 to PORT=8010
```

**B. Missing Environment Variables**
```bash
# Check .env file exists
ls -la infrastructure/docker/.env

# Regenerate if missing
./deploy.sh deploy
```

**C. Docker Image Issues**
```bash
# Rebuild specific service
cd infrastructure/docker
docker compose build --no-cache <service-name>
docker compose up -d <service-name>
```

**D. Volume Permission Issues**
```bash
# Fix volume permissions
docker compose down
docker volume rm $(docker volume ls -q | grep minder)
docker compose up -d
```

---

### 2. Out of Memory Errors

#### Symptoms
- Containers keep restarting
- System becomes slow
- OOMKilled in logs

#### Diagnosis
```bash
# Check resource usage
docker stats

# Check system memory
free -h

# Check container limits
docker inspect minder-ollama | grep -i memory
```

#### Solutions

**A. Reduce Memory Usage**
```bash
# Stop memory-heavy services
docker stop minder-ollama      # If not using AI
docker stop minder-neo4j       # If not using graph features
docker stop minder-influxdb    # If not using time-series
```

**B. Add Memory Limits**
```yaml
# In docker-compose.yml
services:
  ollama:
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 2G
```

**C. Use Smaller AI Models**
```bash
# List available models
docker exec -it minder-ollama ollama list

# Use smaller model
docker exec -it minder-ollama ollama pull llama3.2:3b
```

---

### 3. Database Connection Issues

#### PostgreSQL

**Diagnosis:**
```bash
# Test connection
docker exec -it minder-postgres psql -U minder -d minder

# Check logs
docker logs minder-postgres

# Check if accepting connections
docker exec minder-postgres pg_isready -U minder
```

**Solutions:**
```bash
# Restart PostgreSQL
docker restart minder-postgres

# Reinitialize database
docker compose down -v
docker compose up -d postgres

# Check connection string
# Should be: postgresql://minder:password@postgres:5432/minder
```

#### Redis

**Diagnosis:**
```bash
# Test connection
docker exec -it minder-redis redis-cli -a <password> ping

# Check logs
docker logs minder-redis
```

**Solutions:**
```bash
# Restart Redis
docker restart minder-redis

# Flush cache if corrupted
docker exec -it minder-redis redis-cli -a <password> FLUSHALL
```

#### Qdrant

**Diagnosis:**
```bash
# Check if accessible
curl http://localhost:6333/collections

# Check logs
docker logs minder-qdrant
```

**Solutions:**
```bash
# Restart Qdrant
docker restart minder-qdrant

# Clear collections if corrupted
curl -X DELETE http://localhost:6333/collections/<collection-name>
```

---

### 4. AI Model Issues

#### Ollama Models Not Loading

**Diagnosis:**
```bash
# Check Ollama status
docker exec -it minder-ollama ollama list

# Check logs
docker logs minder-ollama

# Test model
docker exec -it minder-ollama ollama run llama3.2 "test"
```

**Solutions:**

**A. Re-pull Model**
```bash
# Remove and re-pull
docker exec -it minder-ollama ollama rm llama3.2
docker exec -it minder-ollama ollama pull llama3.2
```

**B. Check Disk Space**
```bash
# Check available space
df -h

# Clean if needed
docker system prune -a
```

**C. Use Different Model**
```bash
# Pull smaller model
docker exec -it minder-ollama ollama pull llama3.2:3b

# Update .env
OLLAMA_LLM_MODEL=llama3.2:3b
```

#### Embedding Model Issues

**Diagnosis:**
```bash
# Test embedding
curl http://localhost:11434/api/embeddings -d '{
  "model": "nomic-embed-text",
  "prompt": "test"
}'
```

**Solutions:**
```bash
# Re-pull embedding model
docker exec -it minder-ollama ollama pull nomic-embed-text

# Verify model in .env
grep OLLAMA_EMBEDDING_MODEL infrastructure/docker/.env
```

---

### 5. Network Issues

#### Services Can't Communicate

**Diagnosis:**
```bash
# Check network
docker network ls | grep minder

# Check container networks
docker inspect minder-api-gateway | grep -A 10 Networks

# Test connectivity
docker exec minder-api-gateway ping minder-postgres
```

**Solutions:**

**A. Recreate Network**
```bash
# Remove and recreate
docker network rm minder-network
docker compose up -d
```

**B. Check DNS Resolution**
```bash
# Test from container
docker exec minder-api-gateway nslookup postgres

# Check /etc/hosts
docker exec minder-api-gateway cat /etc/hosts
```

**C. Firewall Issues**
```bash
# Check firewall rules
sudo ufw status

# Allow Docker
sudo ufw allow from 172.16.0.0/12
sudo ufw allow from 192.168.0.0/16
```

---

### 6. Performance Issues

#### Slow API Response

**Diagnosis:**
```bash
# Check response times
time curl http://localhost:8000/health

# Check resource usage
docker stats

# Check database queries
docker exec minder-postgres psql -U minder -d minder -c "SELECT * FROM pg_stat_activity;"
```

**Solutions:**

**A. Enable Caching**
```bash
# Check Redis is working
docker exec -it minder-redis redis-cli -a <password> INFO

# Verify cache configuration
grep CACHE infrastructure/docker/.env
```

**B. Database Optimization**
```sql
-- Add indexes if needed
CREATE INDEX idx_name ON table_name(column_name);

-- Analyze query performance
EXPLAIN ANALYZE your_query;
```

**C. Scale Services**
```yaml
# In docker-compose.yml
services:
  api-gateway:
    deploy:
      replicas: 3
```

---

### 7. Web Interface Issues

#### OpenWebUI Not Loading

**Diagnosis:**
```bash
# Check if running
docker ps | grep openwebui

# Check logs
docker logs minder-openwebui

# Test connection
curl http://localhost:8080/health
```

**Solutions:**
```bash
# Restart service
docker restart minder-openwebui

# Clear browser cache
# Ctrl+Shift+Delete in browser

# Check CORS settings
grep ALLOWED_ORIGINS infrastructure/docker/.env
```

#### Grafana Login Issues

**Diagnosis:**
```bash
# Check logs
docker logs minder-grafana

# Reset admin password
docker exec -it minder-grafana grafana-cli admin reset-admin-password <new-password>
```

**Solutions:**
```bash
# Reset password
docker exec -it minder-grafana grafana-cli admin reset-admin-password admin123

# Check .env for correct password
grep GRAFANA_ADMIN_PASSWORD infrastructure/docker/.env
```

---

### 8. Plugin Issues

#### Plugin Won't Load

**Diagnosis:**
```bash
# Check plugin registry logs
docker logs minder-plugin-registry

# List plugins
curl http://localhost:8001/plugins

# Check plugin files
ls -la src/plugins/
```

**Solutions:**
```bash
# Restart plugin registry
docker restart minder-plugin-registry

# Check plugin permissions
chmod +x src/plugins/*/plugin.py

# Validate plugin YAML
cat config/default_plugins.yml
```

#### Plugin Security Errors

**Diagnosis:**
```bash
# Check security settings
grep PLUGIN_SECURITY infrastructure/docker/.env

# Check plugin signature
curl http://localhost:8001/plugins/<plugin-name>/verify
```

**Solutions:**
```bash
# Adjust security level
PLUGIN_SECURITY_LEVEL=low  # For development

# Add trusted authors
PLUGIN_TRUSTED_AUTHORS=author1,author2
```

---

## 🔍 Debugging Tools

### Interactive Debugging

```bash
# Open shell in container
docker exec -it minder-api-gateway /bin/bash

# Python debugging
docker exec -it minder-api-gateway python -m pdb script.py

# Check environment variables
docker exec minder-api-gateway env | grep MINDER
```

### Log Analysis

```bash
# Follow logs in real-time
docker logs -f --tail=100 minder-api-gateway

# Search logs for errors
docker logs minder-api-gateway 2>&1 | grep -i error

# Export logs
docker logs minder-api-gateway > api-gateway.log

# Analyze with tools
grep ERROR *.log | wc -l
grep WARN *.log | tail -20
```

### Performance Profiling

```bash
# Container resource usage
docker stats --no-stream

# Check bottlenecks
docker top minder-api-gateway

# Memory analysis
docker exec minder-api-gateway cat /proc/meminfo

# Disk I/O
docker exec minder-api-gateway iotop
```

---

## 🚨 Emergency Procedures

### Complete System Reset

```bash
# Stop everything
./deploy.sh stop

# Remove all containers, volumes, images
./deploy.sh clean

# Start fresh
./deploy.sh deploy
```

### Data Recovery

```bash
# Backup volumes
docker run --rm -v minder_postgres_data:/data -v $(pwd):/backup alpine tar czf /backup/postgres-backup.tar.gz -C /data .

# Restore volumes
docker run --rm -v minder_postgres_data:/data -v $(pwd):/backup alpine tar xzf /backup/postgres-backup.tar.gz -C /data
```

### Rollback

```bash
# Stop services
./deploy.sh stop

# Reset to previous commit
git log --oneline
git reset --hard <commit-hash>

# Redeploy
./deploy.sh deploy
```

---

## 📞 Getting Help

### Automated Diagnostics

```bash
# Run full diagnostic
./scripts/health-check.sh > diagnostic-report.txt

# Include in bug report
cat diagnostic-report.txt
```

### Manual Information Collection

```bash
# System info
docker --version
docker compose version
uname -a

# Service status
docker ps > services.txt
docker stats > resources.txt

# Logs
docker logs --tail=500 $(docker ps -q | head -1) > main-service.log

# Configuration
cat infrastructure/docker/.env > config.txt
```

### Report Issues

When reporting issues, include:
1. What you were trying to do
2. What happened (error messages, logs)
3. Expected behavior
4. Steps to reproduce
5. System information (OS, Docker versions)
6. Diagnostic report

---

## 📚 Additional Resources

- **[Architecture Analysis](../ARCHITECTURE_ANALYSIS.md)** - System design review
- **[Quick Start Guide](../QUICKSTART.md)** - Deployment guide
- **[API Documentation](docs/api/)** - API reference
- **[GitHub Issues](https://github.com/your-org/minder/issues)** - Bug reports

---

**Last Updated:** 2026-04-27
**Version:** 2.0.0
