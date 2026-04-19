# Minder Microservices Architecture Design
**Date:** 2026-04-20
**Status:** Approved
**Version:** 1.0

## Executive Summary

Transform Minder from monolithic architecture to domain-driven microservices architecture with plugin deployment capabilities. This transformation enables independent scaling, deployment, and development of business domains while maintaining flexibility for third-party plugin developers.

## Goals

1. **Domain Separation:** Separate business domains into independent services
2. **Plugin Flexibility:** Enable plugins to deploy custom containers
3. **Developer Experience:** Clear documentation for plugin development
4. **Scalability:** Independent scaling per service
5. **Maintainability:** Clear boundaries and responsibilities

## Architecture Overview

### Domain Services

#### 1. Plugin Service (`minder-plugins`)
**Port:** 8001
**Responsibilities:**
- Plugin loading and management
- Hot reload functionality
- Sandbox execution
- Plugin health monitoring
- Plugin observability metrics

**Database:** PostgreSQL (plugin_schema)
**Container:** `minder-plugins:latest`

#### 2. Data Collection Service (`minder-data`)
**Port:** 8002
**Responsibilities:**
- TEFAS fund data collection
- News aggregation
- Weather data collection
- Crypto price tracking
- Scheduled data collection jobs
- Time-series metrics storage

**Database:** InfluxDB
**Container:** `minder-data:latest`

#### 3. Correlation & Analysis Service (`minder-analysis`)
**Port:** 8003
**Responsibilities:**
- Correlation calculations
- Anomaly detection
- Knowledge graph management
- Semantic search
- Vector operations

**Database:** Qdrant + PostgreSQL (correlation_schema)
**Container:** `minder-analysis:latest`

#### 4. Auth Service (`minder-auth`)
**Port:** 8004
**Responsibilities:**
- JWT token generation and validation
- User authentication
- Session management
- Role-based access control

**Database:** PostgreSQL (auth_schema)
**Container:** `minder-auth:latest`

#### 5. API Gateway (`minder-gateway`)
**Port:** 8000 (public)
**Responsibilities:**
- Request routing
- Rate limiting
- Security middleware
- Request aggregation
- Response caching

**Database:** Redis (cache)
**Container:** `minder-gateway:latest`

### Communication Patterns

#### Synchronous Communication (HTTP/REST)
- API Gateway → All services
- Auth Service → Other services (token validation)
- Plugin Service → Data Collection Service (triggers)

#### Asynchronous Communication (Redis Pub/Sub)
- Data Collection Service → Correlation Service (new data events)
- Plugin Service → Observability (metrics/events)
- Correlation Service → API Gateway (analysis results)

#### Message Queue (Redis Lists)
- Job queue for scheduled tasks
- Retry mechanism with exponential backoff
- Dead letter queue for failed jobs

### API Gateway Routing

```
/api/auth/*           → Auth Service (8004)
/api/plugins/*        → Plugin Service (8001)
/api/data/*           → Data Collection Service (8002)
/api/correlations/*   → Correlation Service (8003)
/api/health/*         → All services (health check)
```

## Database Stratification

### PostgreSQL (Relational Data)

**Schema Separation:**
- `auth_schema`: users, sessions, roles
- `plugin_schema`: plugin_metadata, plugin_configs, plugin_health
- `correlation_schema`: correlation_results, analysis_jobs

### InfluxDB (Time-Series Metrics)

**Data Retention:**
- Raw data: 30 days
- Downsampled data: 1 year
**Buckets:**
- `metrics/raw`: All collected metrics
- `metrics/agg_1h`: Hourly aggregates
- `metrics/agg_1d`: Daily aggregates

### Qdrant (Vector Database)

**Collections:**
- `tefas_embeddings`: Fund document vectors
- `news_embeddings`: News article vectors
- `knowledge_graph`: Entity relationship vectors

### Redis (Cache & Queue)

**Usage:**
- Session storage (Auth)
- API response cache
- Pub/Sub messages
- Job queues

### Data Consistency

- **Saga Pattern:** Distributed transactions
- **Eventual Consistency:** Cross-service operations
- **Idempotent Operations:** Retry safety

## Deployment Structure

### Directory Organization

```
minder/
├── services/                    # Microservices
│   ├── gateway/                # API Gateway
│   ├── auth/                   # Auth Service
│   ├── plugins/                # Plugin Service
│   ├── data-collector/         # Data Collection
│   └── analysis/               # Correlation & Analysis
├── plugins/                    # Plugin Packages
│   ├── tefas/
│   ├── news/
│   ├── weather/
│   ├── crypto/
│   └── plugin_template/        # Template for new plugins
├── shared/                     # Common Code
│   ├── models/                 # Pydantic models
│   ├── utils/                  # Utilities
│   ├── config/                 # Shared config
│   └── database/               # Database helpers
├── docs/
│   ├── plugin-development/     # Plugin dev guides
│   ├── api/                    # API documentation
│   └── deployment/             # Deployment guides
├── docker-compose.yml          # Base infrastructure
├── docker-compose.services.yml # Business services
└── docker-compose.plugins.yml  # Plugin services
```

### Docker Compose Structure

**docker-compose.yml** (Infrastructure):
```yaml
services:
  postgres:
  influxdb:
  qdrant:
  redis:
  prometheus:
  grafana:
  alertmanager:
```

**docker-compose.services.yml** (Business Services):
```yaml
services:
  minder-gateway:
  minder-auth:
  minder-plugins:
  minder-data:
  minder-analysis:
```

**docker-compose.plugins.yml** (Plugin Services):
```yaml
services:
  tefas-plugin:
  news-plugin:
  weather-plugin:
  # Plugin-specific services
```

## Plugin Deployment System

### Plugin Package Structure

Each plugin is self-contained with optional custom container:

```
plugins/tefas/
├── plugin.yaml              # Plugin manifest
├── Dockerfile               # Optional: custom container
├── docker-compose.yml       # Optional: plugin services
├── requirements.txt         # Plugin dependencies
├── tefas_module.py          # Plugin implementation
└── collectors/              # Plugin-specific code
    ├── allocation_collector.py
    └── risk_metrics_collector.py
```

### Plugin Manifest (plugin.yaml)

```yaml
name: tefas
version: 1.0.0
description: Turkish ETF fund data collector
author: Minder Team
requires:
  - pandas
  - requests
container:
  image: tefas-plugin:latest
  port: 8005
  environment:
    - DB_HOST=postgres
    - INFLUX_HOST=influxdb
```

### Plugin Dockerfile (Optional)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install plugin dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy plugin code
COPY . .

# Plugin configuration
ENV PLUGIN_NAME=tefas
ENV PLUGIN_PORT=8005

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8005/health || exit 1

CMD ["python", "-m", "tefas_module"]
```

### Plugin Service Discovery

**Plugin Service Discovery Process:**
1. Scan `plugins/` directory for `plugin.yaml` files
2. Load plugin manifests
3. Check if plugin has custom `Dockerfile`
4. If yes: Build and deploy plugin container
5. If no: Load plugin in shared Plugin Service
6. Register plugin with API Gateway

**Plugin Registration:**
- Plugins register with Plugin Service on startup
- Plugin Service maintains plugin registry
- API Gateway discovers plugins via Plugin Service

## Service Scaling

### Horizontal Scaling

**Gateway:** 2-3 replicas (load balanced)
- Stateless
- CPU-intensive (TLS termination)

**Data Collector:** 2 replicas
- Horizontal scaling for parallel collection
- Redis queue for work distribution

**Auth:** 2 replicas
- Stateless with Redis session storage
- Fast reads/writes

### Vertical Scaling

**Analysis:** 1 replica (large instance)
- Heavy computation (correlations, ML)
- Memory-intensive (vector operations)
- Not easily horizontally scalable

## Migration Plan

### Phase 1: Preparation (1-2 days)
- [ ] Create `shared/` library
- [ ] Define service interfaces
- [ ] Create PostgreSQL schemas
- [ ] Setup service templates

### Phase 2: Auth Service Separation (1 day)
- [ ] Extract auth logic to `services/auth/`
- [ ] Create Auth Service container
- [ ] Update API Gateway to route `/api/auth/*`
- [ ] Test authentication flow

### Phase 3: Plugin Service Separation (1-2 days)
- [ ] Extract plugin management to `services/plugins/`
- [ ] Create Plugin Service container
- [ ] Update API Gateway to route `/api/plugins/*`
- [ ] Test plugin loading and execution

### Phase 4: Data Collection Service Separation (2 days)
- [ ] Extract collectors to `services/data-collector/`
- [ ] Create Data Collection Service container
- [ ] Setup InfluxDB integration
- [ ] Test scheduled jobs

### Phase 5: Analysis Service Separation (1-2 days)
- [ ] Extract analysis logic to `services/analysis/`
- [ ] Create Analysis Service container
- [ ] Setup Qdrant integration
- [ ] Test correlation calculations

### Phase 6: API Gateway Completion (1 day)
- [ ] Complete routing configuration
- [ ] Add rate limiting
- [ ] Add caching layer
- [ ] End-to-end testing

**Total:** 7-10 days

## Documentation Requirements

### Plugin Development Guide

**Topics to Cover:**
1. Quick start - Create your first plugin in 10 minutes
2. Plugin structure and files
3. Module interface v2 (register, health_check)
4. Custom container configuration
5. Data collection patterns
6. Testing your plugin
7. Publishing your plugin
8. Best practices and patterns

### API Documentation

**Topics to Cover:**
1. Service endpoints
2. Authentication
3. Rate limiting
4. Error handling
5. Response formats

### Deployment Guide

**Topics to Cover:**
1. Local development setup
2. Docker Compose deployment
3. Production deployment
4. Environment configuration
5. Monitoring and logging
6. Troubleshooting

## Technology Stack

### Services
- **Framework:** FastAPI
- **Python:** 3.11
- **Container:** Docker + Docker Compose
- **Gateway:** Custom FastAPI gateway

### Databases
- **PostgreSQL:** 16 (relational data)
- **InfluxDB:** 2.x (time-series)
- **Qdrant:** Latest (vector DB)
- **Redis:** 7.x (cache + queue)

### Monitoring
- **Prometheus:** Metrics collection
- **Grafana:** Visualization
- **Alertmanager:** Alerting

## Security Considerations

### Service-to-Service Authentication
- JWT tokens for service communication
- Service-specific secrets
- Token rotation policy

### Network Security
- Internal network isolation
- Service discovery via internal DNS
- API gateway as only public entry point

### Plugin Sandboxing
- Resource limits (CPU, memory)
- Execution timeout
- Filesystem restrictions
- Network restrictions

## Success Criteria

- [ ] All services deployed independently
- [ ] API Gateway routing 100% functional
- [ ] Plugin deployment system working
- [ ] Documentation complete and tested
- [ ] Migration completed within 10 days
- [ ] All tests passing
- [ ] Performance baseline established

## Risks and Mitigations

### Risk 1: Distributed Transactions
**Mitigation:** Saga pattern, eventual consistency

### Risk 2: Service Discovery
**Mitigation:** Start with Docker DNS, upgrade to Consul if needed

### Risk 3: Plugin Container Explosion
**Mitigation:** Resource limits, container pooling

### Risk 4: Migration Complexity
**Mitigation:** Incremental migration, phased approach

## Next Steps

1. Create implementation plan with writing-plans skill
2. Setup service templates
3. Begin Phase 1 (Preparation)
4. Create plugin development documentation template

---

**Design Status:** ✅ Approved
**Ready for Implementation Planning:** Yes
**Estimated Implementation Time:** 7-10 days
