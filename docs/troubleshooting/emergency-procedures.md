# Emergency Procedures

**Last Updated:** 2026-07-10

Critical-situation runbooks for the Minder platform (development environment, Raspberry Pi
4). Services run as Docker containers named `minder-<service>`. Compose is at
`docker/compose/docker-compose.yml`; the root `./.env` is the single source of truth for
configuration (`setup.sh` mirrors it to `docker/compose/.env`, which is auto-generated —
do not edit that copy).

Compose commands below assume you are in `docker/compose/` (`cd docker/compose`). You can
also use the `setup.sh` verbs (`start`, `stop`, `restart`, `backup`, `restore`) from the
repo root.

---

## Emergency Scenarios

### 1. Data Loss Emergency

**Symptoms:** tables corrupted, important data missing, backup uncertain.

```bash
# 1. Stop all services
bash setup.sh stop

# 2. Verify the state of the database
docker compose -f docker/compose/docker-compose.yml up -d postgres
docker exec minder-postgres psql -U minder -d minder -c "\dt"

# 3. Locate backups produced by setup.sh
bash setup.sh restore        # interactive restore from managed backups

# 4. (Manual alternative) restore a dump directly
gunzip < /path/to/postgres_backup.sql.gz | \
  docker exec -i minder-postgres psql -U minder

# 5. Bring everything back up
bash setup.sh start

# 6. Verify
docker exec minder-postgres psql -U minder -d minder -c "\dt"
```

**Prevention:** run `bash setup.sh backup` on a schedule; keep backups for at least 7 days;
test restores periodically.

---

### 2. Service Failure Emergency

**Symptoms:** multiple services down; core infrastructure unavailable.

```bash
# 1. Identify failed containers
docker ps -a | grep minder
docker ps -a | grep -i "restarting\|exited"

# 2. Inspect logs of the affected services
docker logs minder-api-gateway --tail 100
docker logs minder-postgres --tail 100
docker logs minder-redis --tail 100

# 3. Attempt recovery (dependencies first)
bash setup.sh restart postgres
bash setup.sh restart redis
bash setup.sh restart api-gateway

# 4. If recovery fails, take an emergency backup before reverting
docker exec minder-postgres pg_dump -U minder -d minder > emergency_backup.sql

# 5. Revert to a previous known-good commit
git log --oneline -10
git checkout <previous-commit-hash>
bash setup.sh start

# 6. Verify a core service
curl http://localhost:8000/health
```

**Prevention:** watch the Prometheus/Grafana stack for alerts; keep recent backups; test
rollbacks.

---

### 3. Security Incident

**Symptoms:** unauthorized access, compromised credentials, suspicious activity.

> Note: this is a development environment; only JWT auth is implemented in api-gateway
> (no RBAC), and Authelia SSO is currently disabled. Treat exposed credentials seriously
> regardless.

```bash
# 1. Stop all services immediately
bash setup.sh stop

# 2. Review logs for suspicious activity
docker logs minder-api-gateway | grep -i "unauthorized\|failed\|401\|403"

# 3. Rotate credentials — ALWAYS edit the ROOT ./.env (single source of truth).
#    Do NOT edit docker/compose/.env: setup.sh overwrites it from ./.env on every
#    start/restart.

# JWT secret is STATELESS — editing ./.env + restart is enough:
NEW_SECRET=$(openssl rand -hex 32)
sed -i "s/JWT_SECRET=.*/JWT_SECRET=$NEW_SECRET/" .env

# POSTGRES_PASSWORD is STATEFUL — editing ./.env alone does NOT rotate the live
# credential (Postgres stores it in its data volume). Update ./.env, then push the
# change into the running database:
NEW_PASS=$(openssl rand -hex 32)
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW_PASS/" .env
bash setup.sh sync-postgres-password   # runs ALTER USER so the live DB matches ./.env

# 4. Re-apply to all containers (start re-syncs ./.env -> docker/compose/.env)
bash setup.sh start

# 5. Monitor for continued activity; document the incident and update policies
```

**Prevention:** rotate secrets regularly; keep the host firewalled; review access logs;
finish the Authelia SSO decision for production.

---

### 4. Resource Exhaustion Emergency

**Symptoms:** host unresponsive, OOM kills, sustained high CPU. Especially relevant on the
Pi's limited RAM.

```bash
# 1. Identify usage
docker stats --no-stream

# 2. Stop the heaviest non-critical services (AI services / inference)
cd docker/compose
docker compose stop rag-pipeline model-management ollama

# 3. Free resources
docker exec minder-redis redis-cli -a "$REDIS_PASSWORD" FLUSHALL   # clears cache

# 4. Restart to reclaim memory
bash setup.sh restart

# 5. Inspect host-level usage
top -b -n 1 | head -20
ps aux --sort=-%mem | head -10

# 6. Long term: set/adjust container resource limits in docker-compose.yml
```

**Prevention:** set container resource limits; alert on memory; keep the model set small on
the Pi.

---

### 5. Disk Space Emergency

**Symptoms:** "No space left on device", containers failing to start.

```bash
# 1. Check disk
df -h
docker system df

# 2. Find large consumers
du -sh /var/lib/docker/* 2>/dev/null | sort -rh | head

# 3. Reclaim space
docker system prune -a --volumes     # WARNING: removes unused volumes too

# 4. Remove old managed backups (keep recent)
find /path/to/backups/ -type f -mtime +7 -delete

# 5. Verify and restart
df -h
bash setup.sh start
```

**Prevention:** monitor disk; rotate logs; prune Docker regularly.

---

## Rollback Procedures

### Full Rollback

```bash
# 1. Stop
bash setup.sh stop

# 2. Back up current state (./.env is source of truth; docker/compose/.env is regenerated)
tar czf rollback_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  .env docker/compose/docker-compose.yml

# 3. Check out the previous version
git checkout <previous-version>

# 4. Start
bash setup.sh start

# 5. Verify
curl http://localhost:8000/health
```

### Partial Rollback (single service)

```bash
cd docker/compose
docker compose stop <service>
docker compose rm -f <service>
docker compose up -d <service>
```

---

## Post-Emergency

### Incident Review
- Document what happened, root cause, and resolution.
- Update these runbooks and the troubleshooting docs if steps were missing or wrong.

### Recovery Verification
```bash
bash setup.sh status
curl http://localhost:8000/health      # api-gateway
curl http://localhost:8004/health      # rag-pipeline
curl http://localhost:8008/health      # graph-rag
```
- Confirm all containers are up, spot-check critical functionality, watch logs and metrics.

---

## Related Documentation

- [Common Issues](common-issues.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
- [Development Guide](../development/development.md)

---

**Last Updated:** 2026-07-10
