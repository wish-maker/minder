# Minder Platform - Security Setup Guide

**Last Updated:** 2026-07-10
**Priority:** P1 - CRITICAL (Must complete before production deployment)

---

## Overview

This guide explains how to configure security credentials and understand the
security posture of the Minder platform.

> **This is a development environment** running on a Raspberry Pi 4. Production
> hardening is **not yet applied**. The measures below describe what exists today
> (secret management, network isolation, reverse-proxy IP whitelisting) plus what
> you must do before any production exposure. **Default credentials must be
> replaced before production deployment.**

### What is actually in place

- **JWT authentication** at the API Gateway (bcrypt password hashing).
- **Traefik v3** reverse proxy (TLS termination, routing). *Not Nginx.*
- **Secrets via a single root `./.env`** file (auto-filled by `setup.sh`,
  mirrored to `docker/compose/.env`, kept at permission `600`).
- **Network isolation**: all storage backends (Postgres, Redis, Qdrant, Neo4j,
  MinIO, RabbitMQ) are internal-only on the `minder-network` Docker network and
  are **not** published to the host.
- **Traefik IP-whitelist middleware** on the dashboard, RabbitMQ management, and
  Neo4j browser routes.

### What is NOT in place (do not assume)

- **No RBAC** — access is gated by holding a valid JWT only.
- **No active SSO / 2FA** — Authelia is defined but disabled (see
  [authentication.md](./authentication.md)).
- **No application-level audit logging** beyond ordinary service/access logs.

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
bash setup.sh start
```

This will:
- Fill every CHANGEME placeholder in `./.env` with a cryptographically secure value
- Leave any value you set yourself untouched (self-healing on every start/restart)
- Keep the generated values visible in `./.env` (so you can record them)
- Set restrictive file permissions (600) on `./.env` and its `docker/compose/.env` copy

### Option 2: Manual Setup

```bash
# root ./.env is the single source of truth
cp .env.example .env

# Optionally set your own values; leave CHANGEME for setup.sh to auto-fill
nano .env

# Auto-fill remaining secrets + mirror ./.env → docker/compose/.env, then start
bash setup.sh start
```

You do not need to generate secrets by hand — `setup.sh` does it. If you prefer
your own, any non-placeholder value you write is preserved.

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

**The single source of truth is the root `./.env`.** Edit that file. `setup.sh`
mirrors it to `docker/compose/.env` (auto-generated — do **not** edit the copy).

```bash
# Minder Platform - Environment Configuration (root ./.env)
# WARNING: Never commit this file to git!

POSTGRES_PASSWORD=your_secure_32_char_password_here
REDIS_PASSWORD=your_secure_32_char_password_here
JWT_SECRET=your_secure_64_char_secret_here
INFLUXDB_TOKEN=your_secure_32_char_token_here
LOG_LEVEL=INFO
```

You normally leave the `CHANGEME` placeholders in place and let `setup.sh`
generate strong values on first `start`. Any non-placeholder value you set
yourself is preserved.

---

## File Permissions

`setup.sh` sets restrictive permissions (`600`) on both `./.env` and its
`docker/compose/.env` copy automatically. To verify or set manually:

```bash
chmod 600 .env
ls -la .env
# Should show: -rw------- (600)
```

This ensures owner read+write only; no group or other access.

---

## Docker Compose Configuration

Compose reads the mirrored `docker/compose/.env`. Services reference these
variables and will fail to start if required secrets are missing. Because the
root `./.env` is the source of truth, always change values there and re-run
`setup.sh start` so the mirror is regenerated.

The stack is invoked as:
```bash
docker compose --file docker/compose/docker-compose.yml <command>
```

---

## Verification Steps

### 1. Check .env File Exists

```bash
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

> **Minder's current mechanism is the single root `./.env`** (auto-filled by
> `setup.sh`, copied to `docker/compose/.env`). There is **one `.env` per machine** —
> no `.env.development`/`.staging`/`.production` layering and no `--env-file` selector.
> For hardened production you may *optionally* layer one of the external systems below
> on top; they are forward-looking, not built in.

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

---

## Credential Rotation

### Quarterly Rotation Schedule

1. **Set new credentials in `./.env`** (the source of truth)
   - Clear the value (or set it to a new one) for the keys you want rotated, e.g.
     `JWT_SECRET=` — `setup.sh` regenerates emptied secret keys on the next start.
   - `setup.sh` backs up `./.env` to `.env.backup-<timestamp>` before any rewrite.

2. **Apply (auto-fills + mirrors `./.env` → `docker/compose/.env`)**
   ```bash
   ./setup.sh stop
   ./setup.sh start
   ```
   > ⚠️ **Stateful secrets** (e.g. `POSTGRES_PASSWORD`) are NOT rotated by editing
   > `./.env` alone — the database keeps its stored password. After changing it, run
   > `./setup.sh sync-postgres-password` to `ALTER USER` the live credential.

3. **Verify all services started**
   ```bash
   ./setup.sh status
   ```

4. **Test application connectivity**
   ```bash
   curl http://localhost:8000/health
   ```

### Emergency Rotation (Compromise Suspected)

If credentials are suspected to be compromised:

1. **Immediate action:** Stop all services
   ```bash
   ./setup.sh stop
   ```

2. **Generate new credentials** — clear the compromised keys in `./.env` (e.g.
   `JWT_SECRET=`, `POSTGRES_PASSWORD=`); `setup.sh` regenerates emptied secret keys.

3. **Rotate the live database password** (stateful — `./.env` alone won't do it)
   ```bash
   ./setup.sh start                    # fills ./.env, mirrors to docker/compose/.env
   ./setup.sh sync-postgres-password   # ALTER USER so the live DB matches ./.env
   ```

4. **Restart all services with the new credentials**
   ```bash
   ./setup.sh start
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
- [ ] Credentials different per deployment (each machine has its own root `./.env`)
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

### Already in place

- **Network isolation** — storage backends (Postgres, Redis, Qdrant, Neo4j,
  MinIO, RabbitMQ) run internal-only on `minder-network` and are not published
  to the host. Only Traefik (80/443) and a small set of observability UIs expose
  host ports.
- **Reverse proxy** — Traefik v3 terminates TLS and routes by Docker labels
  (`exposedByDefault: false`, so nothing is exposed unless explicitly labeled).
- **IP-whitelist middleware** on the Traefik dashboard, RabbitMQ management UI,
  and Neo4j browser routes.
- **JWT authentication** at the API Gateway with Redis-backed rate limiting.
- **Dependency scanning** in CI (see the security workflow: CodeQL + Trivy).

### Recommended before production (not yet applied)

- Enable and enforce SSO/2FA (the deferred Authelia layer) or another auth
  proxy for the management UIs.
- Front all services with HTTPS/TLS certificates (Let's Encrypt via Traefik).
- Add alerting on failed authentication attempts and anomalous access.
- Establish a credential-rotation cadence and review access logs periodically.
- Consider RBAC if multi-tenant / least-privilege access becomes a requirement
  (not implemented today).

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
