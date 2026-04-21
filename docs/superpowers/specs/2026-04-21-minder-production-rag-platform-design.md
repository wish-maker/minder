# Minder Production-Ready RAG Platform - Complete Design Specification

**Date:** 2026-04-21
**Version:** 2.0.0
**Status:** Approved
**Author:** Claude (Sonnet 4.6) + User Collaboration

---

## Executive Summary

Minder is being transformed from a data collection platform into a **production-ready, headless RAG (Retrieval-Augmented Generation) platform** that serves three distinct user personas:

1. **Individual Users** - Personal knowledge management and RAG-powered insights
2. **Enterprise Customers** - Enterprise-grade data correlation and AI-powered analytics
3. **Developers** - Plugin development platform and SDK

**Key Strategic Decisions:**
- **Headless API-First** - REST API is the primary interface (no web UI initially)
- **Microservices Architecture** - 15 core services + independent plugin services
- **v2 Interface Migration** - All plugins will migrate to simplified v2 interface
- **Multi-tenant & Isolated** - User-level resource isolation and quota management
- **Observability Native** - Built-in monitoring, tracing, and alerting

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Core Services (15)](#core-services-layer)
3. [Plugin Services Layer](#plugin-services-layer)
4. [Data Layer](#data-layer)
5. [API Specification](#api-specification)
6. [Security & Compliance](#security--compliance)
7. [Deployment Strategy](#deployment-strategy)
8. [Migration Plan](#migration-plan)
9. [Success Metrics](#success-metrics)

---

## Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    API Gateway Layer (8000)                     │
│  Authentication, Rate Limiting, Request Routing, API Versioning │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Core Services Layer (8001-8015)              │
│                                                                  │
│  Plugin Registry │ Event Bus │ Knowledge Graph │ User Manager   │
│  RAG Pipeline    │ Model Mgmt │ Plugin Generator │ Observability│
│  Workflow Orch   │ Version    │ Alert Manager    │ Audit Log     │
│  Cost Optimizer  │ Webhook    │ Security Scanner                  │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Plugin Services (8020-8099)                  │
│  TEFAS (8020) │ Weather (8021) │ News (8022) │ Crypto (8023)  │
│              + 3rd Party Plugins (80 slots)                     │
└─────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Data Layer                                   │
│  PostgreSQL │ Redis │ InfluxDB │ Qdrant │ S3 │ Ollama │ Prometheus│
└─────────────────────────────────────────────────────────────────┘
```

### Service Port Allocation

**Core Services (15 services):**
- 8000: API Gateway
- 8001: Plugin Registry
- 8002: Event Bus
- 8003: Knowledge Graph
- 8004: RAG Pipeline
- 8005: Model Management
- 8006: Plugin Generator
- 8007: User Manager
- 8008: Observability
- 8009: Workflow Orchestrator
- 8010: Version Control
- 8011: Alert Manager
- 8012: Audit Log
- 8013: Cost Optimizer
- 8014: Webhook Manager
- 8015: Security Scanner

**Plugin Services (80 ports):**
- 8020-8029: Core plugins (TEFAS, Weather, News, Crypto, Network, etc.)
- 8030-8099: 3rd party plugins (70 slots)

---

## Core Services Layer

### 1. API Gateway (Port 8000)

**Responsibilities:**
- JWT authentication and refresh token management
- Role-based access control (RBAC)
- Rate limiting (Redis-backed with per-user quotas)
- Request routing to microservices
- API versioning (/v1/, /v2/)
- Request/response logging
- CORS configuration
- Request ID tracking for distributed tracing

**Technology:**
- FastAPI
- JWT (python-jose)
- Redis for rate limiting
- uvicorn server

**Key Endpoints:**
```
POST   /v1/auth/login
POST   /v1/auth/refresh
POST   /v1/auth/logout
GET    /v1/health
```

---

### 2. Plugin Registry Service (Port 8001)

**Responsibilities:**
- Plugin discovery and registration
- Service discovery (tracks plugin network locations)
- Health monitoring (active + passive health checks)
- Dependency resolution and validation
- Plugin lifecycle management (enable/disable/uninstall)
- Plugin metadata storage

**Technology:**
- FastAPI
- etcd or Consul for service discovery
- PostgreSQL for metadata storage

**Key Endpoints:**
```
GET    /v1/plugins                   - List all plugins
POST   /v1/plugins/install           - Install 3rd party plugin
DELETE /v1/plugins/{name}            - Uninstall plugin
GET    /v1/plugins/{name}/health     - Plugin health status
POST   /v1/plugins/{name}/enable     - Enable plugin
POST   /v1/plugins/{name}/disable    - Disable plugin
```

---

### 3. Event Bus Service (Port 8002)

**Responsibilities:**
- Pub/sub messaging using Redis Streams
- Event persistence and replay
- Dead letter queue for failed events
- Event schema validation
- Multi-tenant event isolation
- Event filtering and routing

**Event Types:**
- `plugin.data_collected`
- `plugin.error`
- `rag.pipeline_completed`
- `model.training_completed`
- `system.alert_triggered`

**Technology:**
- FastAPI
- Redis Streams
- Event schema validation (Pydantic)

**Key Endpoints:**
```
POST   /v1/events/publish            - Publish event
GET    /v1/events/subscribe          - Subscribe to events
GET    /v1/events/replay             - Replay events
```

---

### 4. Knowledge Graph Service (Port 8003)

**Responsibilities:**
- Entity resolution across plugins
- Relationship inference and discovery
- Cross-plugin correlation analysis
- Graph queries and traversals
- Knowledge graph visualization data

**Technology:**
- FastAPI
- Neo4j or RedisGraph
- NetworkX for graph algorithms

**Key Endpoints:**
```
POST   /v1/graph/query               - Query graph
GET    /v1/graph/entities            - List entities
GET    /v1/graph/relationships       - List relationships
POST   /v1/graph/correlate           - Discover correlations
```

---

### 5. RAG Pipeline Service (Port 8004)

**Responsibilities:**
- Knowledge base creation and management
- Document chunking (semantic, fixed, recursive)
- Embedding generation and storage
- Retrieval (semantic search, hybrid search)
- Context window optimization
- LLM generation and streaming
- RAG pipeline orchestration
- Quality metrics and evaluation

**Technology:**
- FastAPI
- Qdrant for vector storage
- OpenAI/Local embeddings
- Ollama/OpenAI for generation

**Key Endpoints:**
```
POST   /v1/rag/knowledge-base        - Create knowledge base
GET    /v1/rag/knowledge-bases       - List knowledge bases
POST   /v1/rag/knowledge-base/{id}/query - Query KB
POST   /v1/rag/pipeline              - Create RAG pipeline
POST   /v1/rag/pipeline/{id}/query   - Query pipeline
GET    /v1/rag/pipeline/{id}/metrics - Pipeline metrics
PUT    /v1/rag/knowledge-base/{id}   - Add documents
```

**RAG Pipeline Configuration:**
```yaml
name: "finance_analyst"
knowledge_base_ids: ["finance_docs", "tefas_data"]
retrieval_config:
  top_k: 5
  similarity_threshold: 0.7
  rerank: true
  search_type: "hybrid"  # semantic, keyword, hybrid
generation_config:
  model: "llama3:70b"
  temperature: 0.7
  max_tokens: 2000
  stream: true
```

---

### 6. Model Management Service (Port 8005)

**Responsibilities:**
- Base model registry (local + remote)
- Model fine-tuning (LoRA, QLoRA)
- Model versioning and deployment
- Model constraints and rate limiting
- Cost tracking per model
- Model performance metrics
- Model A/B testing

**Technology:**
- FastAPI
- Ollama for local models
- OpenAI/Anthropic SDK for remote models
- HuggingFace Transformers for fine-tuning

**Key Endpoints:**
```
GET    /v1/models                    - List all models
POST   /v1/models                    - Register new model
GET    /v1/models/{id}               - Model details
POST   /v1/models/fine-tune          - Fine-tune model
POST   /v1/models/{id}/deploy        - Deploy model
POST   /v1/models/{id}/constraints   - Set model constraints
GET    /v1/models/{id}/metrics       - Model performance
GET    /v1/models/{id}/usage         - Usage statistics
```

**Model Constraints:**
```yaml
rate_limit: 100  # requests per hour
cost_limit: 10.0  # USD per day
allowed_users: [user_ids]
content_filtering: true
max_tokens: 4000
allowed_models: ["llama3:70b", "gpt-4"]
```

---

### 7. Plugin Generator Service (Port 8006)

**Responsibilities:**
- Plugin template generation
- Plugin validation (syntax, dependencies, security)
- Plugin compliance checking (v2 interface)
- Plugin scaffolding
- Plugin testing framework generation
- Plugin documentation generation

**Technology:**
- FastAPI
- Jinja2 for templates
- AST for code analysis
- pylint/bandit for validation

**Key Endpoints:**
```
POST   /v1/plugins/generate          - Generate plugin template
POST   /v1/plugins/validate          - Validate plugin code
GET    /v1/plugins/templates         - List available templates
POST   /v1/plugins/publish           - Publish to registry
```

**Plugin Template Types:**
- `api` - API data collection
- `database` - Database query
- `file` - File processing
- `webhook` - Webhook receiver
- `hybrid` - Custom multi-source

---

### 8. User Manager Service (Port 8007)

**Responsibilities:**
- User registration and authentication
- User profile management
- Team and workspace management
- Role-based access control (RBAC)
- User quota management
- Billing and subscription management
- User-level resource isolation

**Technology:**
- FastAPI
- PostgreSQL for user data
- Stripe for billing

**Key Endpoints:**
```
POST   /v1/auth/register
POST   /v1/auth/login
GET    /v1/user/profile
PUT    /v1/user/profile
GET    /v1/user/quotas
GET    /v1/user/billing
POST   /v1/user/workspaces           - Create workspace
GET    /v1/user/workspaces           - List workspaces
```

**User Quotas:**
```yaml
knowledge_bases: 10
storage_gb: 50
rag_pipelines: 5
models_fine_tuned: 2
rate_limit: 1000  # requests per hour
```

---

### 9. Observability Service (Port 8008)

**Responsibilities:**
- Distributed tracing (request journey tracking)
- Metrics collection (Prometheus format)
- Log aggregation and search
- Real-time dashboards
- Performance monitoring
- Error tracking and alerting
- Custom metrics and alerts

**Technology:**
- FastAPI
- Prometheus for metrics
- Jaeger for tracing
- ELK stack for logs
- Grafana for dashboards

**Key Endpoints:**
```
GET    /v1/observability/traces      - Request traces
GET    /v1/observability/metrics     - System metrics
GET    /v1/observability/logs        - Aggregated logs
GET    /v1/observability/dashboard   - Real-time dashboard
POST   /v1/observability/alerts      - Create alert rule
```

**Metrics Collected:**
- Request latency (p50, p95, p99)
- Request throughput (RPS)
- Error rates
- Resource usage (CPU, memory, disk)
- Database query performance
- Cache hit rates
- Model inference time

---

### 10. Workflow Orchestrator Service (Port 8009)

**Responsibilities:**
- DAG-based workflow definition
- Cron scheduling
- Event-triggered workflows
- Dependency management
- Retry logic with exponential backoff
- Workflow versioning
- Workflow execution history

**Technology:**
- FastAPI
- Airflow or Temporal for orchestration
- Celery for task queue

**Key Endpoints:**
```
POST   /v1/workflows                 - Create workflow
GET    /v1/workflows                 - List workflows
POST   /v1/workflows/{id}/run        - Trigger workflow
GET    /v1/workflows/{id}/runs       - Execution history
PUT    /v1/workflows/{id}            - Update workflow
DELETE /v1/workflows/{id}            - Delete workflow
```

**Example Workflow:**
```yaml
name: "daily_tefas_analysis"
schedule: "0 9 * * *"  # 9 AM daily
steps:
  - name: "collect_tefas_data"
    service: "tefas_plugin"
    action: "collect"
    retry: 3
    timeout: 300

  - name: "update_embeddings"
    service: "rag_pipeline"
    action: "reembed"
    depends_on: ["collect_tefas_data"]

  - name: "generate_report"
    service: "rag_pipeline"
    action: "query"
    depends_on: ["update_embeddings"]
```

---

### 11. Version Control Service (Port 8010)

**Responsibilities:**
- Knowledge base versioning
- RAG pipeline versioning
- Model version management
- Configuration history
- Rollback capability
- A/B testing support
- Diff and comparison

**Technology:**
- FastAPI
- PostgreSQL for version metadata
- S3 for version storage

**Key Endpoints:**
```
POST   /v1/versions/knowledge-base     - Create version
GET    /v1/versions/knowledge-base/{id} - List versions
POST   /v1/versions/knowledge-base/{id}/rollback - Rollback
POST   /v1/versions/pipeline           - Version pipeline
POST   /v1/versions/model              - Version model
GET    /v1/versions/compare            - Compare versions
```

---

### 12. Alert Manager Service (Port 8011)

**Responsibilities:**
- Alert rule management
- Multi-channel notifications (Email, Slack, Discord, SMS)
- Alert escalation
- Incident management
- Alert history and trends

**Alert Types:**
- System alerts (CPU, memory, disk)
- Service alerts (health check failures)
- Data quality alerts (stale data, anomalies)
- Cost alerts (budget exceeded)
- Security alerts (unusual access patterns)

**Technology:**
- FastAPI
- Alertmanager (Prometheus)
- SendGrid for emails
- Slack/Discord webhooks

**Key Endpoints:**
```
POST   /v1/alerts/rules              - Create alert rule
GET    /v1/alerts/rules              - List rules
POST   /v1/alerts/rules/{id}/test    - Test rule
GET    /v1/alerts/incidents          - Active incidents
POST   /v1/alerts/incidents/{id}/ack - Acknowledge incident
```

---

### 13. Audit Log Service (Port 8012)

**Responsibilities:**
- Immutable audit logging
- User action tracking
- Compliance reporting (GDPR, SOC2)
- Log export and archival
- Audit trail queries

**Logged Events:**
- User authentication
- Permission changes
- Data access
- Model deployment
- Pipeline execution
- Configuration changes
- API key usage

**Technology:**
- FastAPI
- PostgreSQL for audit logs
- S3 for archival

**Key Endpoints:**
```
GET    /v1/audit/logs                 - Query logs
GET    /v1/audit/logs/{id}           - Log details
POST   /v1/audit/export              - Export logs
GET    /v1/audit/compliance          - Compliance report
```

---

### 14. Cost Optimizer Service (Port 8013)

**Responsibilities:**
- Real-time cost tracking
- Budget management
- Cost optimization recommendations
- Smart caching (semantic cache)
- Model routing (cost-based)
- Resource usage analytics
- Cost forecasting

**Technology:**
- FastAPI
- Redis for semantic caching
- PostgreSQL for cost tracking

**Key Endpoints:**
```
GET    /v1/cost/usage                - Current costs
GET    /v1/cost/forecasts            - Cost forecasts
POST   /v1/cost/budgets              - Create budget
GET    /v1/cost/recommendations      - Optimization tips
POST   /v1/cost/cache                - Configure cache
```

**Cost Optimization Strategies:**
- Semantic caching (similar queries cached)
- Model routing (simple queries → small models)
- Request batching
- Token optimization
- Scheduled resource scaling

---

### 15. Webhook Manager Service (Port 8014)

**Responsibilities:**
- Webhook configuration and management
- Event-to-webhook routing
- Webhook delivery with retries
- Webhook delivery logs
- Signature verification

**Supported Platforms:**
- Slack
- Discord
- Email (SMTP)
- Microsoft Teams
- Custom webhooks

**Technology:**
- FastAPI
- Celery for async delivery

**Key Endpoints:**
```
POST   /v1/webhooks                  - Create webhook
GET    /v1/webhooks                  - List webhooks
PUT    /v1/webhooks/{id}             - Update webhook
DELETE /v1/webhooks/{id}             - Delete webhook
POST   /v1/webhooks/{id}/test        - Test webhook
GET    /v1/webhooks/{id}/logs        - Delivery logs
```

---

### 16. Security Scanner Service (Port 8015)

**Responsibilities:**
- Vulnerability scanning (dependencies)
- PII detection (data scanning)
- Secret scanning (API keys, passwords)
- Security compliance checks
- Penetration testing
- Security scoring

**Technology:**
- FastAPI
- Safety for secret scanning
- Presidio for PII detection
- Bandit for security scanning

**Key Endpoints:**
```
POST   /v1/security/scan             - Trigger scan
GET    /v1/security/scan/{id}        - Scan results
GET    /v1/security/vulnerabilities  - Vulnerability report
GET    /v1/security/compliance       - Compliance status
POST   /v1/security/scan/pii         - PII scan
```

---

## Plugin Services Layer

### Plugin Service Standards

Every plugin service MUST implement:

**1. Standard Endpoints:**
```python
GET    /health                        - Health check (required)
POST   /collect                       - Manual data collection
GET    /query                         - Plugin-specific query
GET    /metrics                       - Prometheus metrics
GET    /status                        - Plugin status
```

**2. v2 Interface Compliance:**
```python
from core.module_interface_v2 import BaseModule

class MyPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        # REQUIRED: Return plugin metadata
        pass

    # All other methods are OPTIONAL
    async def collect_data(self, since=None):
        # Optional: Override if plugin collects data
        pass

    async def analyze(self):
        # Optional: Override if plugin analyzes data
        pass
```

**3. Docker Configuration:**
```yaml
# Each plugin runs in separate container
services:
  tefas_plugin:
    build: ./plugins/tefas
    ports:
      - "8020:8020"
    environment:
      - PLUGIN_NAME=tefas
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8020/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

### Core Plugins (8020-8029)

| Port | Plugin | Description | Database |
|------|--------|-------------|----------|
| 8020 | TEFAS | Turkish mutual fund data | tefas_db |
| 8021 | Weather | Weather data and forecasts | weather_db |
| 8022 | News | News aggregation and sentiment | news_db |
| 8023 | Crypto | Cryptocurrency price tracking | crypto_db |
| 8024 | Network | System monitoring | network_db |
| 8025-8029 | Reserved | Future plugins | TBD |

### 3rd Party Plugins (8030-8099)

- 70 slots available for community plugins
- Auto-discovery and registration
- Sandboxed execution
- Resource limits per plugin

---

## Data Layer

### Database Strategy

| Database | Purpose | Data Type |
|----------|---------|-----------|
| **PostgreSQL** | Relational data | Users, plugins, versions, audit logs |
| **Redis** | Caching & Queues | Sessions, rate limiting, event bus |
| **InfluxDB** | Time-series | Weather history, crypto prices, metrics |
| **Qdrant** | Vector DB | Embeddings, semantic search |
| **S3/MinIO** | Object Storage | Files, exports, backups |
| **Ollama** | LLM Inference | Local model serving |
| **Prometheus** | Metrics | Time-series metrics |
| **Jaeger** | Tracing | Distributed traces |

### Connection Management

**Connection Pooling:**
- Each service manages its own connection pool
- Async connection pooling (asyncpg for PostgreSQL)
- Automatic reconnection with exponential backoff
- Connection health checks

**Data Isolation:**
- User-level data isolation (multi-tenancy)
- Plugin-level database isolation
- Row-level security (RLS) in PostgreSQL

---

## API Specification

### Response Format

**Success Response:**
```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": {
    "timestamp": "2026-04-21T10:30:00Z",
    "request_id": "uuid-v4",
    "version": "2.0.0",
    "execution_time_ms": 145
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "PLUGIN_NOT_FOUND",
    "message": "Plugin 'xyz' not found in registry",
    "details": {
      "available_plugins": ["tefas", "weather", "news"]
    }
  },
  "meta": {
    "timestamp": "2026-04-21T10:30:00Z",
    "request_id": "uuid-v4",
    "version": "2.0.0"
  }
}
```

### Error Codes

| Code | Description | HTTP Status |
|------|-------------|-------------|
| `AUTHENTICATION_FAILED` | Invalid credentials | 401 |
| `AUTHORIZATION_FAILED` | Insufficient permissions | 403 |
| `RESOURCE_NOT_FOUND` | Resource does not exist | 404 |
| `RATE_LIMIT_EXCEEDED` | Too many requests | 429 |
| `VALIDATION_ERROR` | Invalid input | 400 |
| `PLUGIN_ERROR` | Plugin-specific error | 500 |
| `INTERNAL_ERROR` | Server error | 500 |

---

## Security & Compliance

### Authentication & Authorization

**JWT Authentication:**
- Access tokens: 30 minutes expiration
- Refresh tokens: 7 days expiration
- Token rotation on refresh
- Revocation list in Redis

**RBAC:**
- Roles: `admin`, `user`, `readonly`, `service`
- Permissions: Granular per-resource
- Team-based access control

### Data Security

**Encryption:**
- At rest: AES-256 (database, S3)
- In transit: TLS 1.3
- Key management: HashiCorp Vault or AWS KMS

**PII Protection:**
- Automatic PII detection
- Data redaction
- GDPR compliance tools

### Compliance

**GDPR:**
- Right to be forgotten
- Data export (JSON, CSV)
- Consent management
- Data retention policies

**SOC2:**
- Audit logging
- Access controls
- Change management
- Incident response

---

## Deployment Strategy

### Development Environment

**Docker Compose:**
```bash
cd infrastructure/docker
docker compose up -d
```

**Services Started:**
- All 15 core services
- 5 core plugins
- All databases
- Monitoring stack

### Production Environment

**Kubernetes (Recommended):**
- Helm charts for all services
- Horizontal Pod Autoscaling
- ConfigMap/Secret management
- Ingress for API Gateway
- Persistent volumes for databases

**Infrastructure as Code:**
- Terraform for AWS/GCP/Azure
- Ansible for configuration
- GitHub Actions for CI/CD

---

## Migration Plan

### Phase 1: Foundation (Week 1-2)

**Goals:**
- Setup microservices infrastructure
- Implement API Gateway
- Implement Plugin Registry
- Migrate to v2 interface

**Deliverables:**
- Docker Compose setup
- API Gateway service
- Plugin Registry service
- v2 interface documentation
- 1 plugin migrated to v2 (TEFAS)

### Phase 2: RAG Pipeline (Week 3-4)

**Goals:**
- Implement RAG Pipeline service
- Implement Model Management service
- Setup Qdrant vector database
- Implement knowledge base creation

**Deliverables:**
- RAG Pipeline service
- Model Management service
- Knowledge base API
- Embedding generation
- RAG query API

### Phase 3: Advanced Features (Week 5-6)

**Goals:**
- Implement Observability service
- Implement Workflow Orchestrator
- Implement Version Control
- Implement Alert Manager

**Deliverables:**
- Observability service (Prometheus, Jaeger)
- Workflow Orchestrator service
- Version Control service
- Alert Manager service
- Grafana dashboards

### Phase 4: Production Readiness (Week 7-8)

**Goals:**
- Implement Cost Optimizer
- Implement Security Scanner
- Implement Audit Log service
- Performance optimization
- Load testing

**Deliverables:**
- Cost Optimizer service
- Security Scanner service
- Audit Log service
- Performance benchmarks
- Load test results (1000 RPS target)

---

## Success Metrics

### Technical Metrics

**Performance:**
- API response time: p95 < 200ms
- RAG query time: p95 < 3s
- Uptime: 99.9% (SLA)
- Concurrent users: 1000+

**Quality:**
- Test coverage: >90%
- Code quality score: A
- Security vulnerabilities: 0 critical/high
- Documentation coverage: 100%

### Business Metrics

**User Adoption:**
- Active users: 100+ in first month
- User retention: 70% after 30 days
- Average session duration: 15+ minutes

**Platform Usage:**
- Knowledge bases created: 50+
- RAG queries: 1000+ per day
- Plugins installed: 20+ (including 3rd party)

**Developer Adoption:**
- 3rd party plugins: 5+ in first month
- Plugin downloads: 100+ per month
- Developer accounts: 20+

---

## Next Steps

1. **Review this specification** and confirm all requirements are captured
2. **Create implementation plan** using writing-plans skill
3. **Begin Phase 1 implementation** (Foundation)
4. **Weekly progress reviews** to adjust plan as needed

---

**Document Status:** ✅ Approved
**Next Action:** Create implementation plan
**Estimated Timeline:** 8 weeks to production-ready
**Team Size:** 2-3 developers recommended
