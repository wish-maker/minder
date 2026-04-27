# 🚨 Emergency Procedures

Critical situation handling procedures for the Minder Platform.

---

## ⚠️ Emergency Scenarios

### 1. Data Loss Emergency

**Symptoms:**
- Database tables corrupted
- Important data missing
- Backup unavailable

**Procedure:**

```bash
# 1. Stop all services immediately
docker compose down

# 2. Verify data loss
docker exec minder-postgres psql -U minder -d minder -c "\dt"

# 3. Check if backups exist
ls -lh /backups/minder/

# 4. Restore from backup
gunzip < /backups/minder/postgres_20260419.sql.gz | \
  docker exec -i minder-postgres psql -U minder

# 5. Restart services
docker compose up -d

# 6. Verify data restored
docker exec minder-postgres psql -U minder -d minder -c "SELECT count(*) FROM plugins;"
```

**Prevention:**
- Enable automated backups (cron job)
- Keep backup files for at least 7 days
- Test backup restoration regularly

---

### 2. Service Failure Emergency

**Symptoms:**
- All services down
- Critical infrastructure unavailable
- High impact on operations

**Procedure:**

```bash
# 1. Identify failed services
docker ps -a | grep minder

# 2. Check service logs for errors
docker logs minder-api-gateway --tail 100
docker logs minder-plugin-registry --tail 100
docker logs minder-postgres --tail 100
docker logs minder-redis --tail 100

# 3. Attempt service recovery
docker compose restart api-gateway
docker compose restart plugin-registry
docker compose restart postgres redis

# 4. If recovery fails, revert to last known good state
# Create emergency backup before reverting
docker exec minder-postgres pg_dump -U minder -d minder > emergency_backup.sql
docker exec minder-redis redis-cli --rdb /data/dump.rdb BGSAVE

# 5. Revert to previous version
git log --oneline -10
git checkout <previous-commit-hash>
docker compose up -d

# 6. Verify recovery
curl http://localhost:8000/health
```

**Prevention:**
- Implement health monitoring with alerts
- Keep recent stable backups
- Test rollback procedures regularly

---

### 3. Security Breach Emergency

**Symptoms:**
- Unauthorized access
- Compromised credentials
- Data exfiltration

**Procedure:**

```bash
# 1. Immediate actions
docker compose down  # Stop all services
killall python3      # Kill any suspicious processes

# 2. Isolate affected systems
# Block network access to affected services
ufw deny 8000/tcp
ufw deny 8001/tcp
ufw deny 8004/tcp
ufw deny 8005/tcp

# 3. Check for suspicious activity
docker logs minder-api-gateway | grep -i "unauthorized\|failed\|error"
docker exec minder-postgres psql -U minder -d minder -c "SELECT * FROM audit_log WHERE event='LOGIN_FAILURE';"

# 4. Reset all credentials
# Regenerate database passwords
NEW_PASS=$(openssl rand -hex 32)
sed -i "s/POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$NEW_PASS/" infrastructure/docker/.env

# Regenerate JWT secret
NEW_SECRET=$(openssl rand -hex 32)
sed -i "s/JWT_SECRET=.*/JWT_SECRET=$NEW_SECRET/" infrastructure/docker/.env

# 5. Update all containers with new credentials
docker compose down
docker compose up -d

# 6. Monitor for further suspicious activity
# Enable detailed logging
# Enable intrusion detection
# Review access logs

# 7. Report and document
# Document breach details
# Report to security team
# Update security policies
```

**Prevention:**
- Implement multi-factor authentication
- Use role-based access control
- Regular security audits
- Encryption at rest and in transit
- Intrusion detection systems

---

### 4. Resource Exhaustion Emergency

**Symptoms:**
- System unresponsive
- Processes killed (OOM)
- High CPU/usage

**Procedure:**

```bash
# 1. Identify resource usage
docker stats --no-stream

# 2. Stop non-critical services
docker compose stop minder-rag-pipeline
docker compose stop minder-model-management

# 3. Free resources
# Clear Redis cache
docker exec minder-redis redis-cli FLUSHALL

# Clear memory caches
docker exec minder-api-gateway bash -c "sync && echo 3 > /proc/sys/vm/drop_caches"

# 4. Restart services to free memory
docker compose restart

# 5. Identify resource-intensive processes
top -b -n 1 | head -20
ps aux --sort=-%mem | head -10

# 6. If CPU is the issue
# Kill CPU-intensive processes
kill -9 <PID>

# 7. If memory is the issue
# Reduce container memory limits in docker-compose.yml
# Increase available RAM

# 8. Long-term solution
# Scale horizontally
# Add more resources
# Optimize code
```

**Prevention:**
- Implement resource limits
- Set up monitoring alerts
- Optimize database queries
- Use caching strategies

---

### 5. Disk Space Emergency

**Symptoms:**
- "No space left on device"
- Container cannot start
- Services failing

**Procedure:**

```bash
# 1. Check disk usage
df -h

# 2. Identify large files/directories
du -sh /var/lib/docker/* | sort -rh
du -sh /var/log/* | sort -rh

# 3. Free up disk space

# a. Clean Docker
docker system prune -a --volumes

# b. Clear logs
truncate -s 0 /var/log/syslog
truncate -s 0 /var/log/docker.log
truncate -s 0 /var/log/auth.log

# c. Remove old backups (keep last 7 days)
find /backups/minder/ -type f -mtime +7 -delete

# d. Remove temporary files
rm -rf /tmp/*
rm -rf /var/tmp/*

# 4. Check if space freed
df -h

# 5. Restart services
docker compose up -d

# 6. Monitor for continued disk growth
docker stats --no-stream
```

**Prevention:**
- Set up disk space monitoring
- Implement log rotation
- Automated cleanup scripts
- Regular backup management

---

## 🔄 Rollback Procedures

### Full Rollback

```bash
# 1. Stop all services
docker compose down

# 2. Backup current state (for recovery if needed)
tar czf rollback_backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  infrastructure/docker/.env \
  infrastructure/docker/*.yml \
  /var/lib/docker/volumes/

# 3. Checkout previous version
git checkout <previous-version>

# 4. Start services
docker compose up -d

# 5. Verify rollback
curl http://localhost:8000/health
```

### Partial Rollback

```bash
# 1. Restart affected service only
docker compose down <service-name>
docker compose up -d <service-name>

# 2. Or revert specific container
docker compose stop <service-name>
docker compose rm -f <service-name>
docker compose up -d <service-name>
```

---

## 📞 Emergency Contacts

### Internal
- **On-call:** [Contact person]
- **Database Admin:** [Contact person]
- **DevOps:** [Contact person]

### External
- **Docker Support:** https://docs.docker.com/support/
- **Linux Support:** https://www.linux.org/
- **Security Team:** [Contact]

---

## 📝 Post-Emergency Procedures

### 1. Incident Review

```bash
# Document the incident
echo "[Date] [Service] [Description] [Resolution]" >> /var/log/emergency.log

# Review root cause
# Identify what went wrong
# Document lessons learned

# Update procedures
# Modify troubleshooting guides
# Update documentation
# Update runbooks
```

### 2. Prevention Measures

- Implement monitoring alerts
- Update backup procedures
- Update security policies
- Add emergency drills
- Review and update team skills

### 3. Recovery Verification

- Verify all services are running
- Test critical functionality
- Monitor logs for issues
- Check performance metrics
- Communicate restoration to stakeholders

---

## 📚 Related Documentation

- **[Common Issues](common-issues.md)** - Common problems and solutions
- **[Troubleshooting Guide](README.md)** - Overview
- **[Deployment Guide](../deployment/README.md)** - Deployment troubleshooting
- **[Known Issues](../references/ISSUES.md)** - Known problems

---

## 🤝 Getting Help

**In Emergency:**
1. Follow emergency procedures
2. Contact on-call team
3. Escalate if needed

**After Emergency:**
1. Document incident
2. Review root cause
3. Implement prevention
4. Update procedures

---

**Last Updated:** 2026-04-19
