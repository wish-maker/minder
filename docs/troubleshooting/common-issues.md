# Troubleshooting Guide

## Common Issues and Solutions

### Service Won't Start

#### Problem: Service immediately exits
```bash
# Check logs
docker compose -f infrastructure/docker/docker-compose.yml logs <service>

# Common causes:
# 1. Port already in use
# 2. Missing environment variables
# 3. Database not ready
# 4. Insufficient resources
```

#### Solution: Port Conflicts
```bash
# Find process using port
lsof -i :8000

# Kill process
kill -9 <PID>

# Or change port in docker-compose.yml
```

### Database Issues

#### Problem: Can't connect to database
```bash
# Check database is running
docker exec -it minder-postgres psql -U minder -c "SELECT 1"

# Reset database
docker compose -f infrastructure/docker/docker-compose.yml down -v
docker compose -f infrastructure/docker/docker-compose.yml up -d postgres
```

#### Problem: Database migration failed
```bash
# Check migrations
ls migrations/

# Run migrations manually
docker exec -it minder-postgres psql -U minder -d minder -f /path/to/migration.sql
```

### Memory Issues

#### Problem: Out of memory errors
```bash
# Check memory usage
docker stats

# Increase Docker memory limit (Docker Desktop)
# Settings → Resources → Memory → 8GB+

# Clean up unused resources
docker system prune -a
```

### Network Issues

#### Problem: Services can't communicate
```bash
# Check network
docker network ls | grep minder

# Recreate network
docker network rm docker_minder-network
docker network create docker_minder-network

# Restart services
docker compose -f infrastructure/docker/docker-compose.yml up -d
```

### Plugin Issues

#### Problem: Plugin not loading
```bash
# Check plugin registry
curl http://localhost:8001/plugins

# Check plugin logs
docker logs minder-plugin-registry

# Reload plugin
curl -X POST http://localhost:8001/plugins/<plugin-id>/reload
```

### Authentication Issues

#### Problem: Can't login to Authelia
```bash
# Check Authelia is running
docker ps | grep authelia

# Check Authelia health
curl http://localhost:9091/api/health

# Check Authelia logs
docker logs minder-authelia

# Reset admin password
docker exec -it minder-authelia authelia users list
```

#### Problem: 2FA not working
```bash
# Verify TOTP is configured
# Access http://localhost:9091
# Login → One-Time Password → Check configuration

# Check system time is synchronized
timedatectl status
```

### Security Layer Issues

#### Problem: Traefik dashboard not accessible
```bash
# Check Traefik is running
docker ps | grep traefik

# Check Traefik logs
docker logs minder-traefik

# Verify Traefik health
docker exec minder-traefik wget --quiet --tries=1 --spider http://localhost:8080/ping

# Dashboard may require admin network access
# Try: curl -H "Host: traefik.minder.local" http://localhost/
```

#### Problem: Services returning 401 Unauthorized
```bash
# Check Authelia is healthy
curl http://localhost:9091/api/health

# Verify session cookie
# Check browser developer tools → Application → Cookies

# Test authentication directly
curl -X POST http://localhost:9091/api/verify \
  -H "X-Original-URL: http://localhost:8000/api/v1/plugins" \
  -H "Authorization: Bearer <token>"
```

### Performance Issues

#### Problem: Slow API responses
```bash
# Check resource usage
docker stats

# Enable debug logging
# Set LOG_LEVEL=DEBUG in .env

# Check database connections
docker exec minder-postgres psql -U minder -c "SELECT count(*) FROM pg_stat_activity;"
```

## Getting Help

### Collect Diagnostic Information
```bash
# Save diagnostics
./scripts/diagnostics.sh > diagnostics.txt

# Include in issue report
```

### Useful Commands

```bash
# Service status
docker ps

# Resource usage
docker stats

# Logs
docker compose -f infrastructure/docker/docker-compose.yml logs

# Health check
./scripts/health-check.sh

# Restart service
docker compose -f infrastructure/docker/docker-compose.yml restart <service>
```

### Emergency Reset

```bash
# Full reset (WARNING: Deletes all data)
docker compose -f infrastructure/docker/docker-compose.yml down -v
docker system prune -a
./setup.sh
```
