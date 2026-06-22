# Minder Platform - System Overview

## Current Status

**Platform Version:** 1.0.0
**Last Updated:** 2026-06-22
**Containers Running:** 31 (28 healthy, 3 no-healthcheck, 0 unhealthy)
**Container Health:** 90.3% healthy (28/31 with health checks)
**Core API Services:** 7 (all operational: api-gateway, plugin-registry, marketplace, plugin-state-manager, rag-pipeline, model-management, graph-rag)
**Data Stores:** 7 (all operational: PostgreSQL, Redis, Qdrant, Neo4j, RabbitMQ, MinIO, InfluxDB)
**Deployment Time:** ~5 minutes cold start (sequential startup)
**AI Models:** Ollama runtime with local LLM support
**Deploy Status:** ✅ Clean install proven from zero (docker compose down -v → bash setup.sh start)

**Deferred Features:**
- ⏸️ Authelia SSO/2FA — Disabled pending configuration
- ⏸️ Role-based auth — Auth-only (JWT) implemented

## Architecture Overview

Minder provides a local AI orchestration platform with JWT authentication, RAG pipelines, and monitoring infrastructure.

### System Capabilities

**Core Features:**
- ✅ **Plugin Management** - Manifest-based plugins with lifecycle management
- ✅ **AI Integration** - RAG pipeline, embeddings, local LLM inference
- ✅ **Authentication** - JWT-based auth on all core services
- ✅ **Comprehensive Monitoring** - Prometheus, Grafana, InfluxDB, Alertmanager, Jaeger
- ✅ **Fail-Fast Validation** - Required environment variables enforced

## Service Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         LAYER 8: SECURITY                       │
│  ┌──────────────┐              ┌──────────────┐                │
│  │   Traefik    │ (80/443)     │  Authelia    │ (9091)         │
│  │ Reverse Proxy│              │  SSO + 2FA   │                │
│  └──────────────┘              └──────────────┘                │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                         LAYER 2: CORE APIs                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   API    │ │ Plugin   │ │ Market   │ │  State   │          │
│  │ Gateway  │ │ Registry │ │ place    │ │ Manager  │          │
│  │  :8000   │ │  :8001   │ │  :8002   │ │  :8003   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                         LAYER 3: AI SERVICES                    │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │   RAG    │ │  Model   │ │ TTS/STT  │ │ Fine-Tun │          │
│  │ Pipeline │ │ Mgmt     │ │ Service  │ │  ing     │          │
│  │  :8004   │ │  :8005   │ │  :8006   │ │  :8007   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 1: INFRASTRUCTURE                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │PostgreSQL│ │  Redis   │ │  Neo4j   │ │ Qdrant   │          │
│  │ :5432    │ │  :6379   │ │  :7687   │ │  :6333   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                       │
│  │ RabbitMQ │ │ InfluxDB │ │  MinIO   │                       │
│  │ :5672    │ │  :8086   │ │  :9000   │                       │
│  └──────────┘ └──────────┘ └──────────┘                       │
└─────────────────────────────────────────────────────────────────┘
                                 │
┌─────────────────────────────────────────────────────────────────┐
│                    LAYER 6: OBSERVABILITY                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│  │Prometheus│ │ Grafana  │ │ Jaeger   │ │ Alertmgr │          │
│  │  :9090   │ │  :3000   │ │  :16686  │ │  :9093   │          │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘          │
└─────────────────────────────────────────────────────────────────┘

Total: 31 containers across core services, data stores, and monitoring layers
```

## Service Descriptions

### Security Layer

#### Traefik (Port 80, 443, 8081)
- **Purpose**: Reverse proxy and load balancer
- **Responsibilities**:
  - SSL/TLS termination
  - Request routing
  - Security headers
  - Rate limiting
  - Forward auth integration

#### Authelia (Port 9091) — ⏸️ DISABLED
- **Purpose**: SSO and 2FA authentication
- **Current Status**: Disabled pending configuration (needs DB auto-init + NTP config)
- **Note**: Container stopped and removed from docker-compose.yml

### Core APIs

#### API Gateway (Port 8000)
- **Purpose**: Single entry point for all API requests
- **Responsibilities**:
  - Request routing and load balancing
  - Authentication and authorization
  - Rate limiting and throttling
  - Request/response logging
  - API versioning

#### Plugin Registry (Port 8001)
- **Purpose**: Plugin discovery and lifecycle management
- **Responsibilities**:
  - Plugin registration and discovery
  - Health monitoring
  - Version management
  - Dependency resolution

#### Marketplace (Port 8002)
- **Purpose**: Plugin marketplace and licensing
- **Responsibilities**:
  - Plugin listing and search
  - Licensing and subscriptions
  - User reviews and ratings

#### Plugin State Manager (Port 8003)
- **Purpose**: Central plugin state management
- **Responsibilities**:
  - Plugin state tracking
  - AI tool execution
  - Resource allocation
  - Usage monitoring

#### AI Services (Port 8004)
- **Purpose**: Unified AI/ML services
- **Responsibilities**:
  - RAG pipeline
  - Embedding generation
  - Vector search
  - LLM integration

#### Model Management (Port 8005)
- **Purpose**: Model versioning and fine-tuning
- **Responsibilities**:
  - Model registration
  - Version management
  - Fine-tuning jobs
  - Model deployment

### AI Enhancement Services

#### TTS/STT Service (Port 8006)
- **Purpose**: Text-to-speech and speech-to-text
- **Responsibilities**:
  - Speech synthesis
  - Speech recognition
  - Audio processing

#### Model Fine-tuning (Port 8007)
- **Purpose**: LLM fine-tuning
- **Responsibilities**:
  - Fine-tuning job management
  - Training dataset management
  - Model evaluation

#### OpenWebUI (Port 8080)
- **Purpose**: Web-based chat interface
- **Responsibilities**:
  - Chat UI
  - Model selection
  - RAG integration
  - Tool calling
  - RAG pipeline implementation
  - Embedding generation
  - LLM integration
  - Vector search

### Model Management (Port 8005)
- **Purpose**: Model versioning and fine-tuning
- **Responsibilities**:
  - Model registration
  - Version management
  - Fine-tuning jobs
  - Model deployment

## Data Flow

### 1. Plugin Registration Flow
```
User → API Gateway → Plugin Registry → Database
                ↓
           Health Check → State Manager → Monitoring
```

### 2. AI Request Flow
```
User → API Gateway → AI Services → Embedding Service → Qdrant
                ↓                ↓
           RAG Pipeline ← LLM Service ← Ollama
                ↓
           Response → User
```

### 3. Marketplace Transaction
```
User → API Gateway → Marketplace → Payment Gateway
                ↓              ↓
           License DB → Plugin Registry → Download
```

## Technology Stack

### Backend
- **Framework**: FastAPI (Python 3.11+)
- **Databases**: PostgreSQL 16, Redis 7, Qdrant, Neo4j
- **LLM**: Ollama with local models
- **Authentication**: Authelia + JWT

### Infrastructure
- **Containers**: Docker + Docker Compose
- **Reverse Proxy**: Nginx
- **Monitoring**: Prometheus + Grafana
- **CI/CD**: GitHub Actions

### Frontend
- **Framework**: Next.js 14 (TypeScript)
- **UI Library**: shadcn/ui
- **State Management**: React Query

## Security Architecture

### Authentication Flow
1. User requests → Nginx Proxy
2. Nginx → Authelia (if protected route)
3. Authelia → User authenticates
4. Success → API Gateway
5. API Gateway validates JWT token
6. Request proceeds to service

### Authorization
- **Role-Based Access Control (RBAC)**
- **API Key Authentication**
- **JWT Token Validation**
- **Service-to-Service Authentication**

### Network Security
- **Internal Network Isolation**: All services on `minder-network`
- **External Access**: Only through Nginx proxy
- **Service Discovery**: Internal DNS resolution
- **Secrets Management**: Environment variables only

## Scalability Considerations

### Horizontal Scaling
- **Stateless Services**: API Gateway, Plugin Registry
- **Load Balancing**: Nginx round-robin
- **Database Pooling**: Connection pools in all services
- **Caching Strategy**: Redis for session and API caching

### Vertical Scaling
- **Resource Limits**: Configured per service
- **Auto-scaling**: Based on CPU/Memory metrics
- **Database Optimization**: Indexes, query optimization

## Monitoring & Observability

### Metrics Collection
- **Application Metrics**: Custom business metrics
- **Infrastructure Metrics**: CPU, Memory, Disk
- **Request Tracing**: Distributed tracing

### Logging
- **Structured Logging**: JSON format logs
- **Centralized Logging**: Elasticsearch (future)
- **Log Levels**: DEBUG, INFO, WARNING, ERROR

### Health Checks
- **Service Health**: `/health` endpoint on all services
- **Dependency Health**: Database, Redis, external services
- **Liveness Probes**: Container restart policies

## Development Workflow

### Local Development
```bash
# Start development environment
docker compose -f infrastructure/docker/docker-compose.yml up -d

# Run tests
pytest tests/unit/ -v

# View logs
docker compose -f infrastructure/docker/docker-compose.yml logs -f <service>
```

### Service Development
```bash
# Build specific service
docker compose -f infrastructure/docker/docker-compose.yml build <service>

# Rebuild and restart
docker compose -f infrastructure/docker/docker-compose.yml up -d --build <service>
```

## Deployment Strategies

### Development
- **Environment**: `development`
- **Hot Reload**: Enabled for all services
- **Debug Mode**: Detailed logging

### Staging
- **Environment**: `staging`
- **Load Testing**: Before production
- **Monitoring**: Full observability

### Production
- **Environment**: `production`
- **High Availability**: Multiple instances
- **Auto-scaling**: Based on traffic
- **Rolling Updates**: Zero-downtime deployments

## Future Enhancements

### Phase 2
- [ ] Message Queue (RabbitMQ/Kafka)
- [ ] Distributed Tracing (Jaeger)
- [ ] Centralized Logging (ELK Stack)
- [ ] Service Mesh (Istio)

### Phase 3
- [ ] Multi-region Deployment
- [ ] Disaster Recovery
- [ ] Advanced Analytics
- [ ] ML Pipeline Automation
