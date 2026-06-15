# External Services Configuration Guide

## Overview

Minder platform supports both local Docker services (development) and external cloud services (production). You can switch between them using environment variables without modifying code.

---

## Supported External Services

### 1. Redis (Caching, Rate Limiting, Sessions)

**Providers:**
- AWS ElastiCache
- Redis Labs
- Redis Cloud
- Azure Cache for Redis
- Google Cloud Memorystore

**Configuration:**
```bash
# infrastructure/docker/.env
REDIS_HOST=your-redis-cluster.example.com
REDIS_PORT=6379
REDIS_PASSWORD=your-secure-password
```

**Example: AWS ElastiCache**
```bash
REDIS_HOST=minder-redis.xxxxx.use1.cache.amazonaws.com
REDIS_PORT=6379
REDIS_PASSWORD=your-elasticache-password
```

### 2. PostgreSQL (Primary Database)

**Providers:**
- AWS RDS
- Heroku Postgres
- Neon
- Supabase
- Google Cloud SQL
- Railway

**Configuration:**
```bash
# infrastructure/docker/.env
POSTGRES_HOST=your-postgres-db.example.com
POSTGRES_PORT=5432
POSTGRES_USER=minder
POSTGRES_PASSWORD=your-secure-password
POSTGRES_DB=minder
POSTGRES_SSLMODE=require
```

**Example: AWS RDS**
```bash
POSTGRES_HOST=minder-db.xxxxx.us-east-1.rds.amazonaws.com
POSTGRES_PORT=5432
POSTGRES_USER=minder
POSTGRES_PASSWORD=YourRdsPassword!123
```

**Example: Heroku Postgres**
```bash
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

### 3. Qdrant (Vector Database)

**Providers:**
- Qdrant Cloud
- Self-hosted Qdrant cluster

**Configuration:**
```bash
# infrastructure/docker/.env
QDRANT_HOST=your-cluster.qdrant.io
QDRANT_PORT=6333
QDRANT_API_KEY=your-qdrant-cloud-api-key
QDRANT_TLS=true
```

**Example: Qdrant Cloud**
```bash
QDRANT_HOST=https://your-cluster.qdrant.io
QDRANT_API_KEY=xyz-your-api-key
```

---

## Usage Scenarios

### Scenario 1: Local Development (Default)

All services run in local Docker containers.

```bash
cd infrastructure/docker
docker compose up -d
```

**Services:**
- PostgreSQL: localhost:5432
- Redis: localhost:6379
- Qdrant: localhost:6333

### Scenario 2: Hybrid (Local + External)

Some services local, some external.

**Example: Local Redis + Cloud PostgreSQL**
```bash
# infrastructure/docker/.env
POSTGRES_HOST=aws-rds.amazonaws.com
POSTGRES_PASSWORD=production-password

REDIS_HOST=localhost
REDIS_PORT=6379
```

```bash
cd infrastructure/docker
docker compose up -d postgres redis  # Only start local Redis, use external PostgreSQL
```

### Scenario 3: Full External (Production)

All services external, no local databases.

```bash
# infrastructure/docker/.env
REDIS_HOST=redis-cloud.example.com
POSTGRES_HOST=rds.amazonaws.com
QDRANT_HOST=qdrant-cloud.io
```

```bash
cd infrastructure/docker
docker compose up -d api-gateway plugin-registry  # Only start microservices
```

### Scenario 4: Multi-Environment

Different configurations for dev/staging/production.

**Development (.env.development)**
```bash
POSTGRES_HOST=localhost
REDIS_HOST=localhost
QDRANT_HOST=localhost
```

**Production (.env.production)**
```bash
POSTGRES_HOST=prod-rds.amazonaws.com
REDIS_HOST=prod-redis.xxxxx.use1.cache.amazonaws.com
QdrANT_HOST=https://prod-qdrant.qdrant.io
```

```bash
# Development
docker compose --env-file .env.development up -d

# Production
docker compose --env-file .env.production up -d
```

---

## Service-Specific Configuration

### API Gateway Configuration

The API Gateway reads connection settings from environment variables:

```python
# services/api-gateway/config.py
class Settings:
    REDIS_HOST: str = "minder-redis"           # Default: local container
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "dev_password_change_me"

    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"
```

### Plugin Registry Configuration

```python
# services/plugin-registry/config.py
class Settings:
    POSTGRES_HOST: str = "minder-postgres"       # Default: local container
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "minder"
    POSTGRES_PASSWORD: str = "dev_password_change_me"
    POSTGRES_DB: str = "minder"
```

### RAG Pipeline Configuration

```python
# services/rag-pipeline/config.py (Phase 2)
class Settings:
    QDRANT_HOST: str = "minder-qdrant"         # Default: local container
    QDRANT_PORT: int = 6333
    QDRANT_API_KEY: str = ""  # For Qdrant Cloud
```

---

## Migration Guide

### From Local to External Redis

1. **Create external Redis** (e.g., AWS ElastiCache)
2. **Update .env file:**
   ```bash
   REDIS_HOST=your-elasticache-endpoint.use1.cache.amazonaws.com
   REDIS_PASSWORD=your-elasticache-password
   ```
3. **Restart services:**
   ```bash
   docker compose restart api-gateway plugin-registry
   ```
4. **Verify connection:**
   ```bash
   docker logs minder-api-gateway | grep -i redis
   ```

### From Local to External PostgreSQL

1. **Create external PostgreSQL** (e.g., AWS RDS)
2. **Run init script on external database:**
   ```bash
   psql -h your-rds.amazonaws.com -U minder -d postgres < infrastructure/docker/postgres-init.sql
   ```
3. **Update .env file:**
   ```bash
   POSTGRES_HOST=your-rds.amazonaws.com
   POSTGRES_PASSWORD=your-rds-password
   ```
4. **Restart services:**
   ```bash
   docker compose restart plugin-registry
   ```

### From Local to External Qdrant

1. **Create Qdrant Cloud account**
2. **Get cluster URL and API key**
3. **Update .env file:**
   ```bash
   QDRANT_HOST=your-cluster.qdrant.io
   QDRANT_API_KEY=your-api-key
   ```
4. **Restart RAG Pipeline (Phase 2):**
   ```bash
   docker compose restart rag-pipeline
   ```

---

## Troubleshooting

### Connection Refused Errors

**Problem:** `redis.exceptions.ConnectionError: Error connecting to Redis`

**Solution:**
1. Check external service is reachable: `telnet your-redis-host 6379`
2. Verify security group allows access from your IP
3. Check password is correct

### SSL/TLS Errors

**Problem:** `ssl.SSLError: [SSL: WRONG_VERSION_NUMBER]`

**Solution:**
```bash
# Add TLS configuration
REDIS_TLS=true
POSTGRES_SSLMODE=require
```

### DNS Resolution Errors

**Problem:** `Name or service not known`

**Solution:**
1. Verify host is correct
2. Check DNS settings
3. Try using IP address directly

### Plugin Loading Failures

**Problem:** Plugins fail to load with database errors

**Solution:**
1. Verify external PostgreSQL is accessible: `docker exec minder-plugin-registry ping -c 3 your-postgres-host`
2. Check database exists: `psql -h your-host -U minder -l | grep minder`
3. Run init script if needed

---

## Best Practices

### Security
- Never commit `.env` files with real passwords to git
- Use different passwords for dev/staging/production
- Rotate credentials regularly
- Use IAM authentication where possible (AWS RDS)

### High Availability
- Use Redis Cluster for production
- Use PostgreSQL Multi-AZ deployments
- Enable connection pooling
- Configure retry logic in applications

### Performance
- Use same region for all services (reduce latency)
- Enable Redis persistence
- Configure PostgreSQL connection pooling
- Use Qdrant replication for production

### Monitoring
- Set up health checks for external services
- Configure alerts for connection failures
- Monitor resource usage (CPU, memory, connections)
- Log connection errors for troubleshooting

---

## Quick Reference

| Service | Environment Variable | Default Value | Example External |
|---------|---------------------|---------------|------------------|
| Redis | REDIS_HOST | minder-redis | redis-12345.c1.us-east-1-2.aws.cloud.redislabs.com |
| PostgreSQL | POSTGRES_HOST | minder-postgres | minder-db.xxxxx.us-east-1.rds.amazonaws.com |
| Qdrant | QDRANT_HOST | minder-qdrant | your-cluster.qdrant.io |

---

## Support

For issues or questions:
1. Check service logs: `docker logs <container-name>`
2. Test connectivity: `telnet <host> <port>`
3. Review this guide's troubleshooting section
4. Check service provider documentation
