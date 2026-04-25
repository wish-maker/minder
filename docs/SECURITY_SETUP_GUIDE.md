# Minder Platform - Security Setup Guide

**Last Updated:** 2026-04-23
**Priority:** P1 - CRITICAL (Must complete before production deployment)

---

## Overview

This guide explains how to properly configure security credentials for the Minder platform. **Default credentials must be replaced before production deployment.**

---

## 🚨 Critical Security Issues

The following default credentials are present in the codebase and **MUST be replaced**:

- **POSTGRES_PASSWORD:** `dev_password_change_me` (14 instances)
- **REDIS_PASSWORD:** `dev_password_change_me` (14 instances)
- **JWT_SECRET:** `dev_jwt_secret_change_me` (2 instances)
- **INFLUXDB_TOKEN:** `minder-super-secret-token-change-me-in-production` (2 instances)

**Risk Level:** CRITICAL
- Default credentials allow unauthorized access
- JWT secrets allow token forgery
- All data can be compromised
- Systems can be hijacked

---

## Quick Setup (Recommended)

### Option 1: Automated Setup (Fastest)

```bash
cd infrastructure/docker
./setup-security.sh
```

This will:
- Generate cryptographically secure credentials
- Create `.env` file with proper values
- Set restrictive file permissions (600)
- Display generated values for verification

### Option 2: Manual Setup

```bash
cd infrastructure/docker
cp .env.example .env

# Edit .env with your secure values
nano .env
```

Generate secure passwords:
```bash
# PostgreSQL/Redis/InfluxDB (32 chars)
openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32

# JWT Secret (64 chars)
openssl rand -base64 64 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 64
```

---

## Password Requirements

### PostgreSQL Password
- **Length:** Minimum 32 characters
- **Complexity:** Mix of uppercase, lowercase, numbers, symbols
- **Uniqueness:** Different per environment (dev/staging/prod)
- **Rotation:** Quarterly or after suspected compromise

### Redis Password
- **Length:** Minimum 32 characters
- **Complexity:** Mix of uppercase, lowercase, numbers, symbols
- **Uniqueness:** Different per environment
- **Rotation:** Quarterly or after suspected compromise

### JWT Secret
- **Length:** Minimum 64 characters (recommended 128+)
- **Complexity:** Cryptographically random
- **Uniqueness:** Unique per environment
- **Rotation:** Immediately if suspected compromise
- **Storage:** Never commit to git, use secrets management

### InfluxDB Token
- **Length:** Minimum 32 characters
- **Complexity:** Mix of alphanumeric and symbols
- **Uniqueness:** Different per environment
- **Rotation:** Quarterly or after suspected compromise

---

## Environment File Structure

Create `.env` file in `infrastructure/docker/`:

```bash
# Minder Platform - Environment Configuration
# Generated: 2026-04-23
# WARNING: Never commit this file to git!

POSTGRES_PASSWORD=your_secure_32_char_password_here
REDIS_PASSWORD=your_secure_32_char_password_here
JWT_SECRET=your_secure_64_char_secret_here
INFLUXDB_TOKEN=your_secure_32_char_token_here
ENVIRONMENT=production
LOG_LEVEL=INFO
```

---

## File Permissions

**CRITICAL:** Set restrictive permissions on `.env`:

```bash
chmod 600 .env
```

This ensures:
- Owner (you): read + write
- Group: no permissions
- Others: no permissions

Verify permissions:
```bash
ls -la .env
# Should show: -rw------- (600)
```

---

## Docker Compose Configuration

After creating `.env`, the `docker-compose.yml` file will automatically use these values.

**Note:** The docker-compose.yml file has been updated to **require** environment variables. Services will fail to start if `.env` is missing.

---

## Verification Steps

### 1. Check .env File Exists

```bash
cd infrastructure/docker
test -f .env && echo "✅ .env exists" || echo "❌ .env missing"
```

### 2. Verify No Default Credentials

```bash
grep -l "dev_password_change_me\|dev_jwt_secret_change_me\|minder-super-secret-token" .env
# Should return: "Binary file .env matches" (if found, BAD!)
```

### 3. Check File Permissions

```bash
ls -la .env
# Should show: -rw------- 1 user group size date .env
```

### 4. Test Service Startup

```bash
docker compose up -d
docker compose ps
```

All services should show "Up" status.

---

## Secrets Management (Production)

For production deployment, use a proper secrets management system:

### Docker Secrets (Swarm/Kubernetes)

```yaml
# docker-compose.yml
services:
  postgres:
    secrets:
      - postgres_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password

secrets:
  postgres_password:
    external: true
```

### Kubernetes Secrets

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: minder-credentials
type: Opaque
stringData:
  POSTGRES_PASSWORD: your_secure_password
  REDIS_PASSWORD: your_secure_password
  JWT_SECRET: your_secure_secret
  INFLUXDB_TOKEN: your_secure_token
```

### Environment-Specific Files

```
infrastructure/docker/
├── .env.example        # Template (committed to git)
├── .env.development    # Dev environment (not committed)
├── .env.staging        # Staging environment (not committed)
└── .env.production     # Production environment (not committed)
```

Use with:
```bash
docker compose --env-file .env.production up -d
```

---

## Credential Rotation

### Quarterly Rotation Schedule

1. **Generate new credentials**
   ```bash
   cd infrastructure/docker
   ./setup-security.sh
   ```

2. **Backup current .env**
   ```bash
   cp .env .env.backup.$(date +%Y%m%d)
   ```

3. **Restart services with new credentials**
   ```bash
   docker compose down
   docker compose up -d
   ```

4. **Verify all services started**
   ```bash
   docker compose ps
   ```

5. **Test application connectivity**
   ```bash
   curl http://localhost:8000/health
   ```

### Emergency Rotation (Compromise Suspected)

If credentials are suspected to be compromised:

1. **Immediate action:** Stop all services
   ```bash
   docker compose down
   ```

2. **Generate new credentials**
   ```bash
   ./setup-security.sh
   ```

3. **Change database passwords manually**
   ```bash
   docker compose up -d postgres
   docker exec -it minder-postgres psql -U minder -c "ALTER USER minder PASSWORD 'new_password';"
   ```

4. **Update .env and restart all services**
   ```bash
   docker compose up -d
   ```

5. **Review access logs for suspicious activity**
   ```bash
   docker logs minder-api-gateway --tail 1000
   ```

---

## Security Checklist

Before deploying to production, verify:

- [ ] `.env` file created with unique, strong credentials
- [ ] No default credentials remain in `.env`
- [ ] File permissions set to 600 (owner read/write only)
- [ ] `.env` added to `.gitignore`
- [ ] No `.env` files committed to git repository
- [ ] Credentials different per environment (dev/staging/prod)
- [ ] Credential rotation schedule established
- [ ] Secrets management system configured (production)
- [ ] Access logs monitored for suspicious activity
- [ ] Team trained on credential security procedures

---

## Troubleshooting

### Services Fail to Start

**Symptom:** Services exit immediately or show "unhealthy"

**Diagnosis:**
```bash
docker compose logs postgres
```

**Solution:** Check that `.env` exists and contains valid credentials

### "Password Authentication Failed" Error

**Symptom:** PostgreSQL logs show authentication errors

**Diagnosis:**
```bash
docker exec -it minder-postgres psql -U minder -c "SELECT 1;"
```

**Solution:** Verify `POSTGRES_PASSWORD` in `.env` matches what PostgreSQL expects

### "WRONGPASS invalid username-password pair" Error

**Symptom:** Redis logs show authentication errors

**Diagnosis:**
```bash
docker exec -it minder-redis redis-cli -a $REDIS_PASSWORD ping
```

**Solution:** Verify `REDIS_PASSWORD` in `.env` matches Redis configuration

### JWT Validation Errors

**Symptom:** API requests return 401 Unauthorized

**Diagnosis:** Check API Gateway logs
```bash
docker logs minder-api-gateway --tail 100
```

**Solution:** Verify `JWT_SECRET` in `.env` is same across all services

---

## Additional Security Measures

Beyond credential management, implement these security measures:

### 1. Network Isolation
- Use separate networks for different service tiers
- Implement firewall rules
- Restrict database port exposure (5432, 6379) to internal only

### 2. API Authentication
- Implement JWT-based API authentication
- Add rate limiting per API key
- Use HTTPS/TLS for all API communication

### 3. Monitoring and Alerting
- Set up alerts for failed authentication attempts
- Monitor access logs for suspicious patterns
- Implement intrusion detection systems

### 4. Regular Security Audits
- Scan dependencies for vulnerabilities (dependabot, Snyk)
- Review access logs monthly
- Conduct penetration testing annually
- Keep all services updated with security patches

---

## Resources

- **OWASP Password Security:** https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
- **Docker Secrets:** https://docs.docker.com/engine/swarm/secrets/
- **Kubernetes Secrets:** https://kubernetes.io/docs/concepts/configuration/secret/
- **JWT Best Practices:** https://tools.ietf.org/html/rfc8725

---

## Support

For questions or issues:
1. Check troubleshooting section above
2. Review service logs: `docker compose logs [service]`
3. Open issue in project repository

---

**Remember:** Security is an ongoing process, not a one-time setup. Regular reviews and updates are essential!
