# Docker Secrets Implementation Plan
**Priority**: High (Security Enhancement)
**Current Status**: Ready for Implementation
**Estimated Time**: 2-3 hours
**Risk Level**: Medium (requires careful YAML restructuring)

---

## 🎯 Overview

Implement Docker Secrets to replace environment variables for sensitive data. This will:
- ✅ Remove secrets from environment variables (visible in `docker inspect`)
- ✅ Store secrets in Docker Swarm secrets or file-based secrets
- ✅ Rotate secrets without recreating containers
- ✅ Align with Docker security best practices

---

## 📋 Current State Analysis

### Environment Variables Containing Secrets
```bash
# Database Credentials
POSTGRES_PASSWORD
REDIS_PASSWORD
RABBITMQ_PASSWORD
NEO4J_AUTH

# Application Secrets
JWT_SECRET
JWT_EXPIRATION_MINUTES
WEBUI_SECRET_KEY

# AI Service Configuration
OLLAMA_LLM_MODEL

# Monitoring/Security
AUTHELIA_JWT_SECRET
AUTHELIA_SESSION_SECRET
AUTHELIA_STORAGE_ENCRYPTION_KEY
```

### Security Concerns
- Secrets visible in `docker inspect` output
- Secrets stored in `.env` file (risk of accidental git commit)
- No secret rotation mechanism
- Secrets shared across all containers using same network

---

## 🏗️ Architecture Decision

### Approach: File-Based Docker Secrets

**Why file-based secrets instead of Docker Swarm secrets?**
- ✅ Works with docker-compose (no Swarm required)
- ✅ Simpler implementation for development
- ✅ Can be extended to Swarm secrets later
- ✅ Files can be secured with proper permissions (600)

**Secret Storage Location**: `/root/minder/.secrets/`
**Permission Requirements**: `chmod 600` (owner read/write only)

---

## 🔧 Implementation Plan

### Phase 1: Secret Generation Infrastructure ✅ READY

**File**: `.setup/scripts/generate-secrets.sh`
**Status**: Already created, ready to use

**Features**:
- Generates 12 different secrets
- Outputs to `.secrets/` directory
- Sets proper file permissions (600)
- Creates backup of existing secrets

**Usage**:
```bash
.setup/scripts/generate-secrets.sh
```

**Secrets Generated**:
1. `postgres_password` - Database admin password
2. `redis_password` - Redis authentication
3. `rabbitmq_password` - RabbitMQ authentication
4. `neo4j_password` - Neo4j graph database
5. `minio_access_key` - MinIO object storage
6. `minio_secret_key` - MinIO object storage
7. `influxdb_password` - InfluxDB metrics database
8. `grafana_admin_password` - Grafana dashboard
9. `jwt_secret` - JWT token signing
10. `authelia_jwt_secret` - Authelia JWT
11. `authelia_session_secret` - Authelia sessions
12. `authelia_storage_key` - Authelia database encryption

---

### Phase 2: Docker Compose YAML Restructuring

**Challenge**: Docker Compose doesn't natively support `secrets:` section like Swarm mode

**Solution**: Use `secrets:` section with file-based secrets and compose v3.8+

**Example Pattern**:
```yaml
version: '3.8'

secrets:
  postgres_password:
    file: ./.secrets/postgres_password
  redis_password:
    file: ./.secrets/redis_password

services:
  postgres:
    image: postgres:17.4-alpine
    secrets:
      - postgres_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
```

---

### Phase 3: Step-by-Step Implementation

#### Step 1: Generate Initial Secrets
```bash
# Generate all secrets
.setup/scripts/generate-secrets.sh

# Verify secrets created
ls -la .secrets/

# Verify permissions (should be 600)
ls -l .secrets/*.txt
```

#### Step 2: Update docker-compose.yml Structure

**Add secrets section at top level**:
```yaml
# After the 'networks:' section, add:

secrets:
  postgres_password:
    file: ./.secrets/postgres_password.txt
  redis_password:
    file: ./.secrets/redis_password.txt
  rabbitmq_password:
    file: ./.secrets/rabbitmq_password.txt
  neo4j_password:
    file: ./.secrets/neo4j_password.txt
  influxdb_password:
    file: ./.secrets/influxdb_password.txt
  grafana_password:
    file: ./.secrets/grafana_admin_password.txt
  jwt_secret:
    file: ./.secrets/jwt_secret.txt
  authelia_jwt_secret:
    file: ./.secrets/authelia_jwt_secret.txt
  authelia_session_secret:
    file: ./.secrets/authelia_session_secret.txt
  authelia_storage_key:
    file: ./.secrets/authelia_storage_key.txt
```

#### Step 3: Update Service Definitions

**PostgreSQL Service**:
```yaml
  postgres:
    image: postgres:17.4-alpine
    container_name: minder-postgres
    secrets:
      - postgres_password
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_password
      # Remove: POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

**Redis Service**:
```yaml
  redis:
    image: redis:7.2-alpine
    container_name: minder-redis
    secrets:
      - redis_password
    command: >
      sh -c 'redis-server
      --requirepass "$$(cat /run/secrets/redis_password)"
      --appendonly yes'
    # Remove: REDIS_PASSWORD=${REDIS_PASSWORD}
```

**API Gateway Service**:
```yaml
  api-gateway:
    image: minder/api-gateway:1.0.0
    secrets:
      - jwt_secret
      - redis_password
    environment:
      JWT_SECRET_FILE: /run/secrets/jwt_secret
      REDIS_PASSWORD_FILE: /run/secrets/redis_password
      # Update application code to read from _FILE variables
```

#### Step 4: Update Application Code

**Challenge**: Applications need to read from `_FILE` environment variables

**Solution**: Add file reading logic to application startup

**Python Example** (for API services):
```python
import os

def get_secret(env_var):
    """Read secret from file or environment variable"""
    file_env = f"{env_var}_FILE"
    if os.path.exists(os.environ.get(file_env, '')):
        with open(os.environ[file_env], 'r') as f:
            return f.read().strip()
    return os.environ.get(env_var)

JWT_SECRET = get_secret('JWT_SECRET')
REDIS_PASSWORD = get_secret('REDIS_PASSWORD')
```

---

### Phase 4: Migration Strategy

#### Option A: Big Bang Migration (Recommended for Development)
1. Stop all services: `./setup.sh stop`
2. Generate secrets: `.setup/scripts/generate-secrets.sh`
3. Update docker-compose.yml with secrets
4. Update application code to read from files
5. Start services: `./setup.sh start`
6. Test all services
7. Remove old environment variables from .env

**Pros**: Clean migration, consistent state
**Cons**: Longer downtime, requires testing

#### Option B: Gradual Migration (Production-Friendly)
1. Generate secrets alongside existing env vars
2. Add secrets support to docker-compose.yml
3. Keep environment variables as fallback
4. Update services one-by-one
5. Remove environment variables after migration complete

**Pros**: Zero downtime, gradual rollout
**Cons**: More complex, dual configuration

---

## 🔐 Security Enhancements

### File System Permissions
```bash
# Create secrets directory with proper permissions
mkdir -p .secrets
chmod 700 .secrets

# Ensure all secret files have restricted permissions
chmod 600 .secrets/*.txt

# Add to .gitignore
echo ".secrets/" >> .gitignore
```

### Docker Secrets Benefits
1. **Not visible in `docker inspect`**: Secrets mounted as files, not env vars
2. **Granular access**: Each service gets only secrets it needs
3. **Easy rotation**: Update file, restart service
4. **Audit trail**: File modification times track changes
5. **Backup friendly**: Can backup .secrets/ directory separately

---

## 📊 Impact Assessment

### Services Affected
**High Impact** (require code changes):
- API Gateway (JWT secret)
- Plugin Registry (Redis, JWT)
- Marketplace (Redis, JWT)
- Model Management (Redis, JWT)
- RAG Pipeline (Redis, JWT)
- OpenWebUI (multiple secrets)

**Medium Impact** (configuration changes only):
- PostgreSQL (database password)
- Redis (authentication)
- RabbitMQ (authentication)
- InfluxDB (database password)
- Grafana (admin password)
- Authelia (multiple secrets)

**Low Impact** (no secrets or already secure):
- Traefik (no sensitive config)
- Prometheus (no authentication)
- Ollama (no secrets)
- Qdrant (no authentication)
- Neo4j (uses file-based config)

### Testing Requirements
1. **Unit Tests**: Verify secret reading logic
2. **Integration Tests**: Test service-to-service authentication
3. **End-to-End Tests**: Verify authentication flows
4. **Performance Tests**: Ensure no performance degradation

---

## ⚠️ Risks and Mitigation

### Risk 1: YAML Syntax Complexity
**Impact**: High - Can break all services
**Mitigation**:
- Test YAML syntax with `docker compose config`
- Keep backup of working docker-compose.yml
- Implement incrementally (one service at a time)

### Risk 2: Application Code Changes
**Impact**: Medium - Requires code modifications
**Mitigation**:
- Add fallback logic (try _FILE, then env var)
- Extensive testing before deployment
- Rollback plan ready

### Risk 3: File Permissions
**Impact**: Medium - Secrets could be exposed
**Mitigation**:
- Set proper permissions (600) in generation script
- Verify permissions before starting services
- Add permission check to startup script

### Risk 4: Development Workflow
**Impact**: Low - Developer experience changes
**Mitigation**:
- Document new secret management process
- Update development setup instructions
- Provide helper scripts for common tasks

---

## 🚀 Implementation Timeline

### Phase 1: Preparation (1 hour)
- [x] Secret generation script created
- [ ] Generate initial secrets
- [ ] Set up file permissions
- [ ] Test secret generation

### Phase 2: Infrastructure (1 hour)
- [ ] Update docker-compose.yml with secrets section
- [ ] Update service definitions (one by one)
- [ ] Test YAML syntax validation
- [ ] Create rollback plan

### Phase 3: Application Updates (2-3 hours)
- [ ] Update API Gateway to read from files
- [ ] Update other API services
- [ ] Update OpenWebUI
- [ ] Add fallback logic for compatibility
- [ ] Unit testing

### Phase 4: Migration and Testing (1 hour)
- [ ] Stop services
- [ ] Apply new configuration
- [ ] Start services incrementally
- [ ] Test authentication flows
- [ ] Verify all services healthy

### Phase 5: Cleanup (30 minutes)
- [ ] Remove old environment variables
- [ ] Update documentation
- [ ] Update .gitignore
- [ ] Create backup procedures

**Total Estimated Time**: 5-7 hours

---

## 📝 Post-Implementation Checklist

### Security Validation
- [ ] Verify secrets not visible in `docker inspect`
- [ ] Verify secret file permissions (600)
- [ ] Verify secrets not in git repository
- [ ] Test secret rotation procedure

### Functionality Validation
- [ ] All services start successfully
- [ ] Authentication flows work correctly
- [ ] Service-to-service communication works
- [ ] Monitoring and logging operational

### Documentation Updates
- [ ] Update README.md with secret management
- [ ] Update development setup instructions
- [ ] Create secret rotation guide
- [ ] Update troubleshooting guide

### Operational Procedures
- [ ] Document secret rotation process
- [ ] Create secret backup procedures
- [ ] Update deployment runbook
- [ ] Train team on new process

---

## 🔄 Secret Rotation Procedure

### Manual Rotation (Current)
```bash
# 1. Regenerate specific secret
.setup/scripts/generate-secrets.sh --rotate jwt_secret

# 2. Restart affected services
docker compose restart api-gateway plugin-registry marketplace

# 3. Verify services operational
./setup.sh status
```

### Automated Rotation (Future Enhancement)
```bash
# Script to rotate secrets with zero downtime
.setup/scripts/rotate-secrets.sh --service api-gateway --secret jwt_secret
```

---

## 🎯 Success Criteria

### Technical Requirements
- ✅ Secrets not visible in `docker inspect` output
- ✅ All services operational with secrets
- ✅ Secret rotation works without downtime
- ✅ File permissions properly set (600)
- ✅ No secrets in git repository

### Operational Requirements
- ✅ Documentation updated
- ✅ Team trained on new process
- ✅ Backup procedures in place
- ✅ Monitoring for secret access

### Security Requirements
- ✅ Compliance with security best practices
- ✅ Audit trail for secret changes
- ✅ Proper secret lifecycle management
- ✅ Emergency access procedures

---

## 📞 Support and Rollback

### If Implementation Fails
1. **Immediate Rollback**: Restore backup docker-compose.yml
2. **Restart Services**: `./setup.sh restart`
3. **Verify Health**: `./setup.sh status`
4. **Document Issues**: Record what went wrong
5. **Retry Later**: Address issues and attempt again

### Common Issues and Solutions

**Issue**: Services fail to start after secrets implementation
**Solution**: Check file paths, verify permissions, check logs

**Issue**: Application can't read secret files
**Solution**: Verify _FILE environment variables, check file reading logic

**Issue**: YAML syntax errors
**Solution**: Use `docker compose config` to validate, check indentation

---

## 🏁 Next Steps

### Immediate Actions
1. Review this implementation plan
2. Test secret generation script
3. Choose migration strategy (Big Bang vs Gradual)
4. Schedule implementation window

### Future Enhancements
1. Implement Docker Swarm secrets for production
2. Add automated secret rotation
3. Integrate with external secret managers (Vault, AWS Secrets Manager)
4. Implement secret versioning and rollback

---

**Plan Status**: 🟢 READY FOR IMPLEMENTATION
**Priority**: HIGH (Security Enhancement)
**Estimated Completion**: 5-7 hours
**Risk Level**: MEDIUM (requires careful testing)

**Recommendation**: Implement during maintenance window or development sprint. System is currently stable and operational, so this can be scheduled strategically.

---

**Document Version**: 1.0
**Last Updated**: 2026-05-05 17:20:00
**Next Review**: After implementation completion
