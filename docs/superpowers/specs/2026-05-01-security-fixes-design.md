# Security Fixes Design

**Date:** 2026-05-01
**Priority:** HIGH - Security vulnerabilities
**Status:** Design Phase

## Problem Statement

Critical security vulnerabilities identified:

### 1. Default Password in .env.example
```bash
# Line 81: DEFAULT PASSWORD - CRITICAL SECURITY RISK!
GRAFANA_ADMIN_PASSWORD=minder123
```
**Risk:** Anyone with repository access knows default credentials.

### 2. Duplicate Redis Configuration
```bash
# Lines 12-14 and 27-30: Redis configuration duplicated
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password_here

# ... later ...

REDIS_HOST=localhost  # DUPLICATE!
REDIS_PORT=6379       # DUPLICATE!
```
**Risk:** Configuration confusion, possible connection issues.

### 3. Weak Security Defaults
```bash
# Line 81: ENVIRONMENT=development
ENVIRONMENT=development
```
**Risk:** Production deployments run in development mode.

## Proposed Solutions

### 1. Remove Default Password

**Current (.env.example Line 81):**
```bash
GRAFANA_ADMIN_PASSWORD=minder123  # ❌ DEFAULT PASSWORD
```

**Fixed:**
```bash
# Grafana Admin Password
# SECURITY: Generate a strong password using:
# openssl rand -base64 32
# Example: AbCdEf123456XyZ7890123456789012==
GRAFANA_ADMIN_PASSWORD=changeme_on_first_deploy
```

**Alternative: Auto-generate in setup.sh**
```bash
# In setup.sh:
generate_secure_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

GRAFANA_PASSWORD=$(generate_secure_password)
echo "GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASSWORD" >> infrastructure/docker/.env
echo "✅ Generated secure Grafana password"
```

### 2. Remove Duplicate Redis Configuration

**Current (.env.example Lines 27-30):**
```bash
# Redis Configuration
REDIS_HOST=localhost  # ❌ DUPLICATE
REDIS_PORT=6379       # ❌ DUPLICATE
```

**Fixed: REMOVE these lines entirely** (Lines 27-30)

Keep only Lines 12-14:
```bash
# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=your_redis_password_here
```

### 3. Change Default Environment

**Current (.env.example Line 82):**
```bash
ENVIRONMENT=development  # ❌ Production deployments run in dev mode
```

**Fixed:**
```bash
# Environment: development | staging | production
ENVIRONMENT=production
```

### 4. Add Security Checklist

**Add to .env.example:**
```bash
# ============================================================================
# SECURITY CHECKLIST - Complete before deploying to production
# ============================================================================
# [ ] Change all passwords (use strong, unique passwords)
# [ ] Generate JWT_SECRET_KEY using: openssl rand -base64 64
# [ ] Generate WEBUI_SECRET_KEY using: openssl rand -base64 64
# [ ] Set ENVIRONMENT=production
# [ ] Review and update ALLOWED_ORIGINS
# [ ] Enable rate limiting (RATE_LIMIT_ENABLED=true)
# [ ] Review plugin security settings
# [ ] Configure SSL/TLS certificates
# [ ] Set up firewall rules
# [ ] Review backup retention policy
# ============================================================================
```

### 5. Add Password Generation Script

**New script: `scripts/generate-secrets.sh`**
```bash
#!/bin/bash
# Minder Platform - Generate Secure Secrets

echo "🔐 Generating secure secrets for Minder Platform..."

# Generate Grafana password
GRAFANA_PASS=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

# Generate JWT secret
JWT_SECRET=$(openssl rand -base64 64)

# Generate WebUI secret
WEBUI_SECRET=$(openssl rand -base64 64)

# Generate Redis password
REDIS_PASS=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

# Generate PostgreSQL password (if not set)
POSTGRES_PASS=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-25)

# Output to .env file
cat > infrastructure/docker/.env << EOF
# Auto-generated secrets - $(date)
NEVER COMMIT THIS FILE TO VERSION CONTROL

# Database Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=minder
POSTGRES_USER=minder
POSTGRES_PASSWORD=$POSTGRES_PASS

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=$REDIS_PASS

# Grafana
GRAFANA_ADMIN_PASSWORD=$GRAFANA_PASS

# Security
JWT_SECRET_KEY=$JWT_SECRET
WEBUI_SECRET_KEY=$WEBUI_SECRET

# Environment
ENVIRONMENT=production
EOF

echo "✅ Secrets generated successfully"
echo "⚠️  SAVE THESE PASSWORDS IN A SECURE LOCATION:"
echo ""
echo "   Grafana Admin: $GRAFANA_PASS"
echo "   PostgreSQL:   $POSTGRES_PASS"
echo "   Redis:        $REDIS_PASS"
echo ""
echo "📝 Store these passwords in a password manager."
```

### 6. Add .env Validation

**Update `setup.sh` to validate .env:**
```bash
validate_env_file() {
    local env_file="infrastructure/docker/.env"

    if [ ! -f "$env_file" ]; then
        echo "❌ .env file not found. Run: ./scripts/generate-secrets.sh"
        exit 1
    fi

    # Check for default passwords
    if grep -q "minder123" "$env_file"; then
        echo "❌ ERROR: Default password detected in .env"
        echo "   Change GRAFANA_ADMIN_PASSWORD immediately"
        exit 1
    fi

    # Check for placeholder values
    if grep -qE "changeme|your_.*_here|CHANGE_ME" "$env_file"; then
        echo "❌ ERROR: Placeholder values found in .env"
        echo "   Replace all 'changeme' and 'your_*_here' values"
        exit 1
    fi

    # Check environment
    if ! grep -q "ENVIRONMENT=production" "$env_file"; then
        echo "⚠️  WARNING: ENVIRONMENT not set to production"
    fi

    echo "✅ .env validation passed"
}
```

### 7. Update docker-compose.yml

**Add health check for Grafana:**
```yaml
grafana:
  # ... existing config ...
  healthcheck:
    test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000/api/health"]
    interval: 30s
    timeout: 10s
    retries: 3
    start_period: 40s
```

### 8. Add Security Documentation

**Create: `docs/guides/security-hardening.md`**
```markdown
# Security Hardening Guide

## Pre-Deployment Security Checklist

### 1. Password Security
- [ ] Generate unique passwords for all services
- [ ] Use password manager for storage
- [ ] Never reuse passwords
- [ ] Rotate passwords quarterly

### 2. Secrets Management
- [ ] Never commit .env to version control
- [ ] Use environment variables for secrets
- [ ] Consider HashiCorp Vault for production

### 3. Network Security
- [ ] Configure firewall rules
- [ ] Use internal networks for services
- [ ] Enable SSL/TLS for all endpoints
- [ ] Review CORS settings

### 4. Application Security
- [ ] Enable rate limiting
- [ ] Configure JWT expiration
- [ ] Review plugin security settings
- [ ] Enable 2FA for admin accounts

## Post-Deployment Security

### Monitoring
- Review Grafana dashboards for anomalies
- Check logs for suspicious activity
- Monitor authentication failures
- Track API usage patterns

### Incident Response
- Have a security incident response plan
- Know how to quickly rotate credentials
- Have contact information for security team
```

### 9. Add Pre-Commit Hook

**Update `.pre-commit-config.yaml`:**
```yaml
repos:
  - repo: local
    hooks:
      - id: check-env-secrets
        name: Check for secrets in code
        entry: |
          ! grep -r "minder123\|changeme\|your_.*_here" \
            infrastructure/docker/.env.example || echo "⚠️  Found placeholder values"
        language: system
        pass_filenames: false
```

### 10. CI/CD Security Scanning

**Update `.github/workflows/ci.yml`:**
```yaml
security-scan:
  runs-on: ubuntu-latest
  steps:
    - name: Checkout code
      uses: actions/checkout@v4

    # Remove "|| true" - fail on security issues
    - name: Run Bandit security linter
      run: |
        pip install bandit[toml]
        bandit -r services/ src/ -f json -o bandit-report.json
      # ❌ REMOVE: || true

    - name: Run Safety check
      run: |
        pip install safety
        safety check --json > safety-report.json
      # ❌ REMOVE: || true

    # Fail build on high-severity issues
    - name: Check for secrets
      run: |
        if grep -r "minder123\|changeme" infrastructure/docker/; then
          echo "❌ Found placeholder values"
          exit 1
        fi
```

## Implementation Order

### Phase 1: Critical Security Fixes (1 hour)
1. ✅ Remove default password from .env.example
2. ✅ Remove duplicate Redis configuration
3. ✅ Change ENVIRONMENT default to production
4. ✅ Add security checklist to .env.example

### Phase 2: Automation (2 hours)
5. ✅ Create generate-secrets.sh script
6. ✅ Add .env validation to setup.sh
7. ✅ Update pre-commit hooks

### Phase 3: Documentation (1 hour)
8. ✅ Create security hardening guide
9. ✅ Update README with security notes
10. ✅ Add .env.example to .gitignore (if not already)

### Phase 4: CI/CD Updates (1 hour)
11. ✅ Fix CI workflow security scans
12. ✅ Add secrets detection to CI
13. ✅ Remove "|| true" from security checks

## Testing Strategy

1. **Test generate-secrets.sh** - Verify all secrets generated
2. **Test .env validation** - Verify placeholder detection
3. **Test setup.sh validation** - Verify pre-flight checks
4. **Test CI/CD** - Verify security scans fail appropriately

## Success Criteria

✅ No default passwords in .env.example
✅ No duplicate configuration entries
✅ ENVIRONMENT defaults to production
✅ Automated secret generation available
✅ .env validation prevents insecure deployments
✅ CI/CD fails on security issues
✅ Security documentation complete

## Estimated Timeline

- **Phase 1**: 1 hour
- **Phase 2**: 2 hours
- **Phase 3**: 1 hour
- **Phase 4**: 1 hour
- **Testing**: 2 hours

**Total**: 7 hours (1 day)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users skip password generation | HIGH | Validation in setup.sh prevents deployment |
| Secrets committed to repo | HIGH | Pre-commit hook + .gitignore entry |
| CI/CD false positives | MEDIUM | Tune security scan rules |
| Production uses development mode | HIGH | Validation in health check |

---

## Approval Required

Before implementing:
1. ✅ Confirm password generation approach (auto vs manual)
2. ✅ Confirm validation strictness (block vs warn)
3. ✅ Confirm CI/CD failure policy (fail fast vs warnings)

**Next Steps:** Upon approval, proceed to implementation plan.
