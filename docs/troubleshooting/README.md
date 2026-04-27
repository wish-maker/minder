# 🔧 Troubleshooting Guide

Common problems and solutions for the Minder Platform.

---

## 📖 Documentation Structure

### Common Issues
- **[Common Issues](common-issues.md)** - Frequently encountered problems

### Emergency Procedures
- **[Emergency Procedures](emergency-procedures.md)** - Critical situation handling

---

## 🚀 Quick Troubleshooting

### Services Won't Start

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
docker logs <container-name> --tail 100
```

**See:** [Common Issues](common-issues.md) for more details

---

### High Memory Usage

**Symptoms:**
- Services slow or unresponsive
- OOM kills in logs

**Solutions:**
```bash
# Restart services
docker compose restart

# Clear Redis cache
docker exec minder-redis redis-cli FLUSHALL

# Check memory usage
docker stats
```

**See:** [Common Issues](common-issues.md) for more details

---

### Database Connection Issues

**Symptoms:**
- Services cannot connect to databases
- Connection errors in logs

**Solutions:**
```bash
# Check database status
docker logs minder-postgres --tail 50
docker logs minder-redis --tail 50

# Restart databases
docker compose restart postgres redis

# Check database connection
docker exec minder-postgres pg_isready
```

**See:** [Common Issues](common-issues.md) for more details

---

### Plugin Load Failures

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

**See:** [Common Issues](common-issues.md) for more details

---

## 🚨 Emergency Procedures

**See:** [Emergency Procedures](emergency-procedures.md)

### Rollback Procedure

```bash
# Stop all services
docker compose down

# Start previous version
docker-compose.yml.backup
docker compose up -d
```

### Emergency Backup

```bash
# Quick database backup
docker exec minder-postgres pg_dump -U minder -d minder > emergency_backup.sql

# Quick config backup
tar czf config_backup.tar.gz infrastructure/docker/.env infrastructure/docker/*.yml
```

---

## 📚 Related Documentation

- **[Deployment Guide](../deployment/README.md)** - Deployment troubleshooting
- **[API Reference](../api/README.md)** - API endpoint issues
- **[Known Issues](../references/ISSUES.md)** - Known problems

---

## 🤝 Getting Help

- **GitHub Issues:** https://github.com/wish-maker/minder/issues
- **Documentation:** /root/minder/docs/
- **Community:** (to be added)

---

**Last Updated:** 2026-04-19
