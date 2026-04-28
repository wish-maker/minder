# Deployment Documentation

Production deployment guides and operational procedures for Minder Platform.

## Deployment Guides

### [Production Deployment](production.md)
**Essential** - Complete production deployment guide.

Covers:
- Pre-deployment checklist
- Security configuration
- Resource requirements
- Step-by-step deployment
- Verification procedures
- Rollback strategies

### [Monitoring Setup](monitoring.md)
**Essential** - Monitoring and observability setup.

Covers:
- Prometheus configuration
- Grafana dashboards
- Alertmanager setup
- Log aggregation
- Metrics collection
- Health checks

### Hardware Optimization
See [HARDWARE_OPTIMIZATION.md](HARDWARE_OPTIMIZATION.md) for:
- Performance tuning
- Resource optimization
- Scaling strategies
- Cost optimization

## Deployment Methods

### Method 1: Automated (Recommended)
```bash
git clone https://github.com/your-org/minder.git
cd minder
./deploy.sh
```

### Method 2: Manual
See [Production Deployment](production.md) for detailed manual deployment.

## Pre-Deployment Checklist

### Security
- [ ] Change all default passwords
- [ ] Configure SSL/TLS certificates
- [ ] Set up firewall rules
- [ ] Enable rate limiting
- [ ] Review CORS settings

### Infrastructure
- [ ] Verify system requirements
- [ ] Ensure Docker is installed
- [ ] Configure reverse proxy
- [ ] Set up monitoring
- [ ] Plan backup strategy

### Configuration
- [ ] Review environment variables
- [ ] Configure SMTP settings
- [ ] Set up backup jobs
- [ ] Test disaster recovery

## Production Best Practices

### Security
1. **Use strong passwords** - Minimum 32 characters
2. **Enable HTTPS** - SSL/TLS certificates
3. **Configure firewalls** - Restrict access
4. **Regular updates** - Keep dependencies current
5. **Monitor logs** - Security auditing

### Performance
1. **Resource limits** - Set appropriate limits
2. **Horizontal scaling** - Scale stateless services
3. **Load balancing** - Distribute traffic
4. **Caching** - Redis optimization
5. **Database tuning** - Connection pooling

### Reliability
1. **Health checks** - Monitor all services
2. **Auto-restart** - Restart policies
3. **Backups** - Regular backup jobs
4. **Disaster recovery** - Test recovery procedures
5. **Monitoring** - Alert on issues

## Scaling

### Horizontal Scaling
```bash
# Scale API Gateway to 3 instances
docker compose -f infrastructure/docker/docker-compose.yml up -d --scale api-gateway=3
```

### Vertical Scaling
Edit `docker-compose.yml` to adjust resource limits:
```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'
      memory: 2G
```

## Monitoring

### Health Checks
```bash
# Automated health check
./scripts/health-check.sh

# Manual check
curl http://localhost:8000/health
```

### Metrics
- **Prometheus**: http://localhost:9090
- **Grafana**: http://localhost:3000
- **Alertmanager**: http://localhost:9093

### Logs
```bash
# View all logs
docker compose -f infrastructure/docker/docker-compose.yml logs -f

# View service logs
docker logs minder-api-gateway -f
```

## Backup & Recovery

### Database Backup
```bash
# Automated daily backup
docker exec minder-postgres pg_dump -U minder > backup.sql
```

### Restore
```bash
# Restore from backup
docker exec -i minder-postgres psql -U minder < backup.sql
```

## Troubleshooting

Having deployment issues?

- [Common Issues](../troubleshooting/common-issues.md)
- [Emergency Procedures](../troubleshooting/emergency-procedures.md)

## Support

For production issues:
1. Check logs: `./scripts/logs.sh`
2. Run diagnostics: `./scripts/diagnostics.sh`
3. Review troubleshooting guide
4. Contact support: support@minder-platform.com
