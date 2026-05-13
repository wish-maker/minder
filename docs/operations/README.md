# Operations Guide - Minder Platform

**Version:** 1.0.0
**Last Updated:** 2026-05-02

---

## Overview

This guide covers operational tasks for managing the Minder Platform in production environments. The `setup.sh` script provides enterprise-grade lifecycle management capabilities.

## Lifecycle Management Commands

### Installation & Setup

```bash
./setup.sh                          # Full installation (recommended)
./setup.sh install                  # Explicit install command
```

**What it does:**
- Checks prerequisites (Docker, Docker Compose)
- Creates environment configuration
- Sets up Docker networks
- Initializes databases
- Starts all 32 services
- Downloads AI models automatically
- Verifies health of all services

**Expected time:** ~9 minutes

### Service Management

```bash
./setup.sh start                    # Start all services
./setup.sh stop                     # Stop all services
./setup.sh stop --clean             # Stop + prune dangling images
./setup.sh restart                  # Restart all services
```

**Use cases:**
- **start:** Start services after system reboot or manual stop
- **stop:** Graceful shutdown for maintenance
- **stop --clean:** Stop services and clean up unused Docker resources
- **restart:** Apply configuration changes or recover from errors

### Status & Monitoring

```bash
./setup.sh status                   # Live health overview + resource usage
./setup.sh status --json            # Machine-readable JSON output
./setup.sh health                   # Run health checks
./setup.sh logs [service] [lines]   # Tail logs (all or specific service)
```

**Status command output:**
- Running containers with health status
- Port mappings
- Resource usage (CPU, memory)
- Volume information
- Network status

**JSON output format:**
```json
{
  "services": [
    {
      "name": "api-gateway",
      "status": "healthy",
      "health": "healthy",
      "ports": ["0.0.0.0:8000->8000/tcp"]
    }
  ],
  "total": 23,
  "healthy": 23,
  "unhealthy": 0,
  "timestamp": "2026-05-02T12:00:00Z"
}
```

### Operational Commands

#### Doctor Command (NEW!)

```bash
./setup.sh doctor
```

**What it checks:**
- ✅ Disk space availability (minimum 10GB free required)
- ✅ Port conflicts (checks all required ports)
- ✅ Secret validation (verifies password strength)
- ✅ Image availability (verifies Docker images exist)
- ✅ Version drift detection (compares running vs configured versions)

**Use cases:**
- Pre-deployment validation
- Troubleshooting service failures
- Post-incident verification
- System health audits

**Example output:**
```
🩺 Running system diagnostics...

✅ Disk Space: 45.2GB free (10GB minimum required)
✅ Port Conflicts: None detected
✅ Secrets: All secrets meet minimum requirements
✅ Docker Images: All required images available
⚠️  Version Drift: 2 images can be updated
   - traefik: v3.1.5 → v3.1.6
   - grafana: 11.3.0 → 11.4.0
```

#### Shell Access (NEW!)

```bash
./setup.sh shell                    # Interactive menu for service selection
./setup.sh shell api-gateway        # Direct access to specific service
```

**Use cases:**
- Debugging service issues
- Running one-off commands
- Inspecting service configuration
- Database operations (psql, redis-cli)

**Example:**
```bash
./setup.sh shell postgres
# psql -U minder -d minder
# \dt  # List tables
# \q   # Quit
```

#### Migration Command (NEW!)

```bash
./setup.sh migrate                  # Run all pending migrations
./setup.sh migrate head             # Migrate to latest version
./setup.sh migrate +1               # Migrate one step
./setup.sh migrate -1               # Rollback one step
```

**Use cases:**
- Database schema updates
- Applying Alembic migrations
- Rolling back failed migrations

**Database support:**
- PostgreSQL (primary database)
- Neo4j (graph database)
- InfluxDB (time-series data)
- Qdrant (vector database)

### Message Queue (NEW!)

RabbitMQ is now included as the message queue solution for the Minder platform.

#### Start RabbitMQ

```bash
docker compose -f infrastructure/docker/docker-compose.yml up -d rabbitmq
```

**Access:**
- AMQP port: 5672
- Management UI: http://localhost:15672
- Default credentials: minder / (set RABBITMQ_PASSWORD in .env)

#### Check RabbitMQ Status

```bash
docker ps | grep rabbitmq
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/overview
```

#### Management UI

Access the RabbitMQ Management UI at http://localhost:15672 for:
- Queue monitoring
- Message browsing
- Connection management
- Policy configuration

#### Usage Examples

See `examples/rabbitmq_example.py` for complete usage examples:

```bash
# Install dependencies
pip install -r examples/requirements.txt

# Run examples
python examples/rabbitmq_example.py
```

**Integration with Minder services:**
- API Gateway → Plugin Registry (plugin tasks)
- Event broadcasting (pub/sub)
- Dead Letter Queue (error handling)

#### RabbitMQ in Production

**Before deploying to production:**
1. Set strong RABBITMQ_PASSWORD in .env
2. Enable clustering for high availability
3. Configure resource limits (memory, disk)
4. Set up monitoring (Prometheus exporter)
5. Define queue policies (max length, TTL)

**Monitoring:**
```bash
# Check queue depth
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/queues

# Get message rates
curl -u minder:${RABBITMQ_PASSWORD} http://localhost:15672/api/queues/%2F/plugin.crypto
```

**Policies:**
```bash
# Set max length on queue
curl -u minder:${RABBITMQ_PASSWORD} -X PUT \
  -H "content-type:application/json" \
  -d '{"max-length": 10000}' \
  http://localhost:15672/api/policies/%2F/queue-length-policy
```

### Data Management

#### Backup (ENHANCED!)

```bash
./setup.sh backup
```

**What it backs up:**
- ✅ PostgreSQL databases (all 5 databases)
- ✅ Neo4j graph data
- ✅ InfluxDB time-series data
- ✅ Qdrant vector collections
- ✅ RabbitMQ queue definitions
- ✅ Environment configuration (.env file)

**Backup location:**
```
backups/minder-backup-YYYYMMDD-HHMMSS/
├── postgres_backup.sql
├── neo4j_backup.dump
├── influxdb_backup.tar
├── qdrant_backup.tar
├── rabbitmq-definitions.json
└── env_backup.txt
```

**Backup retention:**
- Automatic timestamp in directory name
- No automatic cleanup (manual management)
- Compressed archives to save space

**Use cases:**
- Pre-migration backups
- Scheduled backups (cron job)
- Disaster recovery preparation

#### Restore (NEW!)

```bash
./setup.sh restore                  # Interactive selection
./setup.sh restore backups/minder-backup-20260502-120000/
```

**What it restores:**
- PostgreSQL databases from SQL dump
- Neo4j data from backup dump
- InfluxDB data from tar archive
- Qdrant collections from backup
- RabbitMQ queue definitions from JSON
- Environment configuration

**Interactive mode:**
```
Available backups:
1. minder-backup-20260502-120000 (2.3GB)
2. minder-backup-20260501-080000 (2.1GB)

Select backup to restore [1-2]: 1

⚠️  WARNING: This will overwrite existing data!
Continue? [y/N]: y

✅ PostgreSQL restored
✅ Neo4j restored
✅ InfluxDB restored
✅ Qdrant restored
✅ Environment restored

🔄 Restarting services...
```

**Use cases:**
- Disaster recovery
- Rollback to previous state
- Migrating to new server

### Update Management

#### Check Updates (NEW!)

```bash
./setup.sh update --check
```

**What it checks:**
- Docker Hub for official images
- GitHub Container Registry (GHCR)
- Quay.io for alternative registries
- Version constraint validation
- Compatibility checking

**Example output:**
```
🔍 Checking for available updates...

Updates available:
  ✅ traefik:v3.1.5 → v3.1.6 (bug fixes)
  ✅ grafana:11.3.0 → 11.4.0 (new features)
  ✅ redis:7.2-alpine → 7.4-alpine (security updates)

Total: 3 updates available
Run './setup.sh update' to apply updates
```

**Use cases:**
- Pre-update planning
- Security vulnerability assessment
- Change management preparation

#### Apply Updates

```bash
./setup.sh update
```

**What it does:**
1. Pulls latest compatible Docker images
2. Rebuilds custom Minder service images
3. Prompts for service restart
4. Verifies health after restart

**Update process:**
```
🔄 Pulling latest images...
  ✅ Pulled traefik:v3.1.6
  ✅ Pulled grafana:11.4.0
  ✅ Pulled redis:7.4-alpine

🔨 Rebuilding custom images...
  ✅ Built api-gateway:1.0.0
  ✅ Built plugin-registry:1.0.0

⚠️  Services need to restart to apply updates
Restart now? [y/N]: y

🔄 Restarting services...
  ✅ All services restarted
  ✅ Health checks passing
```

**Use cases:**
- Regular maintenance updates
- Security patch application
- Feature upgrades

### Uninstallation

```bash
./setup.sh uninstall --keep-data    # Remove services, keep data volumes (safe)
./setup.sh uninstall --purge        # Stop and DELETE all data (destructive)
```

**--keep-data (safe):**
- Stops and removes containers
- Preserves all data volumes
- Can be restarted with `./setup.sh start`

**--purge (destructive):**
- Stops and removes containers
- Deletes all data volumes
- Removes Docker networks
- Cannot be undone

**Use cases:**
- **--keep-data:** Temporary shutdown, server migration
- **--purge:** Complete system cleanup, starting fresh

## CI/CD Integration

### Environment Variables

```bash
# Non-interactive mode (for automation)
NONINTERACTIVE=1 ./setup.sh install

# Dry-run mode (preview only)
DRY_RUN=1 ./setup.sh update

# Verbose output (debugging)
VERBOSE=1 ./setup.sh doctor

# Skip version check (faster startup)
SKIP_VERSION_CHECK=1 ./setup.sh start
```

### JSON Output for Monitoring

```bash
./setup.sh status --json
```

**Integration examples:**

**Python:**
```python
import json
import subprocess

output = subprocess.check_output(['./setup.sh', 'status', '--json'])
status = json.loads(output)

if status['unhealthy'] > 0:
    print(f"Alert: {status['unhealthy']} services unhealthy!")
```

**Bash:**
```bash
#!/bin/bash
# health-check.sh

UNHEALTHY=$(./setup.sh status --json | jq '.unhealthy')

if [ "$UNHEALTHY" -gt 0 ]; then
    echo "CRITICAL: $UNHEALTHY services unhealthy"
    exit 2
fi

echo "OK: All services healthy"
exit 0
```

**Prometheus Exporter:**
```python
from prometheus_client import Gauge, start_http_server
import json, subprocess, time

service_health = Gauge('minder_service_health', 'Service health status', ['service'])

while True:
    output = subprocess.check_output(['./setup.sh', 'status', '--json'])
    status = json.loads(output)

    for service in status['services']:
        value = 1 if service['health'] == 'healthy' else 0
        service_health.labels(service['name']).set(value)

    time.sleep(60)
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
./setup.sh logs <service>

# Run diagnostics
./setup.sh doctor

# Restart service
./setup.sh restart

# Check for port conflicts
lsof -i :<port>
```

### High Memory Usage

```bash
# Check resource usage
./setup.sh status

# Clean up unused resources
./setup.sh stop --clean

# Restart services
./setup.sh start
```

### Database Issues

```bash
# Access database shell
./setup.sh shell postgres

# Check database health
./setup.sh health

# Restore from backup
./setup.sh restore <backup-archive>
```

### Update Failures

```bash
# Check what's available
./setup.sh update --check

# Run diagnostics
./setup.sh doctor

# Manual image pull
docker pull <image>:<tag>

# Rebuild service
docker compose -f infrastructure/docker/docker-compose.yml build <service>
```

## Scheduled Operations

### Cron Jobs

**Daily backup (2:00 AM):**
```bash
0 2 * * * cd /root/minder && ./setup.sh backup > /var/log/minder-backup.log 2>&1
```

**Weekly health check (Monday 8:00 AM):**
```bash
0 8 * * 1 cd /root/minder && ./setup.sh doctor > /var/log/minder-doctor.log 2>&1
```

**Monthly update check (1st of month):**
```bash
0 9 1 * * cd /root/minder && ./setup.sh update --check > /var/log/minder-update.log 2>&1
```

**Weekly cleanup (Sunday 3:00 AM):**
```bash
0 3 * * 0 cd /root/minder && ./setup.sh stop --clean > /var/log/minder-cleanup.log 2>&1
```

## Best Practices

### Pre-Deployment Checklist

- [ ] Run `./setup.sh doctor` to verify system health
- [ ] Run `./setup.sh backup` before making changes
- [ ] Run `./setup.sh update --check` to review available updates
- [ ] Review logs for any errors or warnings
- [ ] Verify sufficient disk space (>10GB free)

### Maintenance Windows

**Recommended schedule:**
- **Daily:** Automated backups (2:00 AM)
- **Weekly:** Health checks and review (Monday 8:00 AM)
- **Monthly:** Update and patch application (1st of month)
- **Quarterly:** Major version upgrades and testing

### Monitoring

**Key metrics to monitor:**
- Service health status (all services should be healthy)
- Disk space usage (maintain >10GB free)
- Memory usage (alert if >90%)
- CPU usage (alert if >80% sustained)
- API response times (alert if >5s)

### Backup Strategy

**3-2-1 rule:**
- **3** copies of data (production, backup, offsite)
- **2** different storage types (local, cloud)
- **1** offsite backup (remote location)

**Retention policy:**
- Daily backups: 7 days
- Weekly backups: 4 weeks
- Monthly backups: 12 months

## Support

For operational issues:
1. Check logs: `./setup.sh logs`
2. Run diagnostics: `./setup.sh doctor`
3. Review troubleshooting guide: `docs/troubleshooting/common-issues.md`
4. Check GitHub Issues: https://github.com/wish-maker/minder/issues
5. Contact support: support@minder-platform.com

---

**Last Updated:** 2026-05-02
**Documentation Version:** 1.0.0
