# Troubleshooting

Common issues and solutions for Minder Platform.

## Quick Help

### Most Common Issues

1. **Services won't start**
   → Check logs: `docker logs <service>`
   → Verify ports: `lsof -i :8000`
   → Restart: `docker compose restart <service>`

2. **Database connection errors**
   → Check database: `docker exec minder-postgres pg_isready -U minder`
   → Verify password in `.env`
   → Restart database: `docker compose restart postgres`

3. **Port already in use**
   → Find process: `lsof -i :8000`
   → Kill process: `kill -9 <PID>`
   → Or change port in `docker-compose.yml`

## Troubleshooting Guides

### [Common Issues](common-issues.md)
**Essential** - Frequently encountered issues and solutions.

Covers:
- Installation issues
- Service startup problems
- Database issues
- Network issues
- Performance issues

### [Emergency Procedures](emergency-procedures.md)
**Critical** - Crisis management and recovery.

Covers:
- Full system recovery
- Service failures
- Data corruption
- Security incidents
- Disaster recovery

## Diagnostic Tools

### Health Check
```bash
# Automated health check
./scripts/health-check.sh

# Manual check
curl http://localhost:8000/health
```

### Diagnostics Script
```bash
# Run diagnostics
./scripts/diagnostics.sh

# Shows:
# - Service status
# - Resource usage
# - Configuration issues
# - Performance metrics
```

### Logs
```bash
# View all logs
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# View specific service
docker logs minder-api-gateway -f

# Last 100 lines
docker logs minder-api-gateway --tail 100

# Since specific time
docker logs minder-api-gateway --since 1h
```

### Container Status
```bash
# All containers
docker ps

# Container details
docker inspect minder-api-gateway

# Resource usage
docker stats
```

## Issue Categories

### Installation Issues

**Problem**: Services won't start after setup
```
Solution:
1. Check Docker is running: docker info
2. Verify ports are available: lsof -i :8000
3. Check logs: docker compose logs
4. Restart: docker compose restart
```

**Problem**: Out of memory errors
```
Solution:
1. Check available memory: free -h
2. Reduce service limits in docker-compose.yml
3. Close other applications
4. Add swap space if needed
```

### Service Issues

**Problem**: Service restarting continuously
```
Solution:
1. Check logs: docker logs <service>
2. Verify configuration: cat .env
3. Check dependencies: docker compose ps
4. Restart with rebuild: docker compose up -d --build <service>
```

**Problem**: Service unhealthy
```
Solution:
1. Wait longer (some services take time)
2. Check health endpoint: curl http://localhost:PORT/health
3. Review logs: docker logs <service>
4. Verify dependencies are healthy
```

### Database Issues

**Problem**: Database connection refused
```
Solution:
1. Check database is running: docker exec minder-postgres pg_isready
2. Verify password in .env matches
3. Check network: docker network ls
4. Restart database: docker compose restart postgres
```

**Problem**: Database corrupted
```
Solution:
1. Stop services: docker compose down
2. Remove volumes: docker compose down -v
3. Restart: ./setup.sh
4. Restore from backup if available
```

### Performance Issues

**Problem**: Slow response times
```
Solution:
1. Check resource usage: docker stats
2. Scale services: docker compose up -d --scale api-gateway=3
3. Review logs for errors
4. Check database performance
```

**Problem**: High memory usage
```
Solution:
1. Check stats: docker stats
2. Reduce resource limits in docker-compose.yml
3. Restart services: docker compose restart
4. Clear caches: docker system prune -a
```

### Security Issues

**Problem**: Cannot authenticate
```
Solution:
1. Check Authelia is running: docker ps | grep authelia
2. Verify credentials: admin/admin123 (default)
3. Check Authelia logs: docker logs minder-authelia
4. Reset password if needed
```

**Problem**: Rate limit errors
```
Solution:
1. Wait for rate limit to reset (1 minute)
2. Check Redis is running: docker logs minder-redis
3. Adjust rate limits in configuration
4. Use different API key if applicable
```

## Getting Help

### Self-Service

1. **Check Documentation**
   - [Common Issues](common-issues.md)
   - [Emergency Procedures](emergency-procedures.md)
   - [API Reference](../api/reference.md)

2. **Run Diagnostics**
   ```bash
   ./scripts/diagnostics.sh
   ```

3. **Check Logs**
   ```bash
   ./scripts/logs.sh
   ```

### Community Support

- 📚 [Documentation Index](../)
- 💬 [GitHub Discussions](https://github.com/your-org/minder/discussions)
- 🐛 [GitHub Issues](https://github.com/your-org/minder/issues)

### Professional Support

For enterprise support:
- 📧 Email: support@minder-platform.com
- 🔒 Priority support
- 📞 SLA guarantees

## Reporting Issues

When reporting issues, please include:

1. **Minder Platform version**
   ```bash
   git log -1
   ```

2. **System information**
   ```bash
   ./scripts/diagnostics.sh > diagnostics.txt
   ```

3. **Service logs**
   ```bash
   docker logs <service> > service.log
   ```

4. **Steps to reproduce**
   - What you were trying to do
   - What you expected to happen
   - What actually happened

5. **Error messages**
   - Full error output
   - Screenshots if applicable

## Emergency Contacts

### Critical Issues
- 📧 Email: emergency@minder-platform.com
- 📱 PagerDuty: +1-XXX-XXX-XXXX

### Business Hours
- 📧 Email: support@minder-platform.com
- 💬 Slack: #minder-support

## Prevention

### Regular Maintenance
```bash
# Weekly health check
./scripts/health-check.sh

# Monthly cleanup
./scripts/cleanup.sh

# Quarterly updates
./scripts/update_libraries.sh
```

### Monitoring
- Set up Grafana dashboards
- Configure Alertmanager alerts
- Review logs regularly
- Monitor resource usage

### Backups
```bash
# Daily database backup
docker exec minder-postgres pg_dump -U minder > backup_$(date +%Y%m%d).sql

# Weekly volume backup
docker run --rm -v docker_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres_$(date +%Y%m%d).tar.gz /data
```
