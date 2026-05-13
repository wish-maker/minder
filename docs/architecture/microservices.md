# Microservices Architecture

Detailed microservices architecture for Minder Platform.

## Current Service Status

**Total Services:** 32
**Healthy Services:** 29 (90.6% with health checks)
**No-Healthcheck Services:** 3 (minimal exporters - normal)
**Unhealthy Services:** 0
**Test Coverage:** 98.7% (116 passing tests)
**Cold Start Time:** ~5 minutes (sequential startup)
**AI Models:** Ollama runtime with local LLM support
**Production Readiness:** 99%

## Overview

Minder Platform implements a microservices architecture with 32 independent services, each running in its own Docker container across 8 architectural layers.

## Service Communication

### Synchronous Communication
- **REST APIs** - HTTP/JSON between services
- **API Gateway** - Single entry point for external requests
- **Service Discovery** - Docker DNS for service resolution

### Asynchronous Communication
- **Redis Pub/Sub** - Event messaging (planned)
- **Message Queues** - Task queues (planned)

## Service Categories

### Security Layer

#### Traefik (Reverse Proxy)
**Purpose**: Single entry point, SSL termination, load balancing

**Responsibilities**:
- Request routing
- SSL/TLS termination
- Load balancing
- Security headers
- Rate limiting
- Forward auth integration

**Configuration**: `infrastructure/docker/traefik/`

**Health Check**: `http://localhost:8081/ping`

#### Authelia (SSO & 2FA)
**Purpose**: Centralized authentication and authorization

**Responsibilities**:
- Single Sign-On (SSO)
- Two-Factor Authentication (2FA)
- User management
- Access control
- Session management
- Brute force protection

**Storage**: PostgreSQL (`minder_authelia`)

**Configuration**: `infrastructure/docker/authelia/`

**Health Check**: `http://localhost:9091/api/health`

### Core Infrastructure

#### PostgreSQL
**Purpose**: Primary relational database

**Databases**:
- `minder` - Main application database
- `minder_marketplace` - Marketplace database
- `minder_authelia` - Authelia database
- `tefas_db`, `weather_db`, `news_db`, `crypto_db` - External data sources

**Connection Pool**: 20 connections default

**Backup**: Daily automated backups

#### Redis
**Purpose**: Caching, sessions, rate limiting

**Use Cases**:
- Session storage
- Rate limiting (sorted sets)
- API response caching
- Pub/Sub messaging (planned)

**Persistence**: AOF enabled

#### Qdrant
**Purpose**: Vector database for embeddings

**Use Cases**:
- RAG pipeline embeddings
- Semantic search
- Similarity matching

**Collections**: Multiple collections per use case

#### Ollama
**Purpose**: Local LLM inference

**Models**:
- llama3.2
- mistral
- qwen2.5
- nomic-embed-text
- mxbai-embed-large

**API**: http://localhost:11434

#### Neo4j
**Purpose**: Graph database for dependencies

**Use Cases**:
- Plugin dependency graph
- Relationship mapping
- Path finding

**Plugins**: APOC (A Procedure On Cypher)

### Core APIs

#### API Gateway (Port 8000)
**Purpose**: Single entry point for all API requests

**Responsibilities**:
- Request routing
- Authentication (JWT)
- Rate limiting
- Request validation
- Response formatting

**Routes**: `/api/v1/*`

#### Plugin Registry (Port 8001)
**Purpose**: Plugin discovery and lifecycle management

**Endpoints**:
- `POST /api/v1/plugins/register` - Register plugin
- `GET /api/v1/plugins` - List plugins
- `GET /api/v1/plugins/{id}` - Get plugin details
- `PUT /api/v1/plugins/{id}` - Update plugin
- `DELETE /api/v1/plugins/{id}` - Delete plugin

#### Marketplace (Port 8002)
**Purpose**: Plugin marketplace and licensing

**Endpoints**:
- `GET /api/v1/marketplace/plugins` - List marketplace plugins
- `POST /api/v1/marketplace/purchase` - Purchase plugin
- `GET /api/v1/marketplace/licenses` - List licenses

#### State Manager (Port 8003)
**Purpose**: Plugin state and AI tool execution

**Endpoints**:
- `GET /api/v1/state/plugins/{id}` - Get plugin state
- `POST /api/v1/state/plugins/{id}/execute` - Execute plugin
- `GET /api/v1/state/plugins/{id}/status` - Get execution status

#### AI Services (Port 8004)
**Purpose**: RAG pipeline and embeddings

**Endpoints**:
- `POST /api/v1/rag/query` - RAG query
- `POST /api/v1/embeddings` - Generate embeddings
- `GET /api/v1/rag/collections` - List collections

**Pipeline**:
1. Query → 2. Embed → 3. Search Qdrant → 4. Retrieve context → 5. LLM generate

#### Model Management (Port 8005)
**Purpose**: Model versioning and fine-tuning

**Endpoints**:
- `GET /api/v1/models` - List models
- `POST /api/v1/models` - Register model
- `POST /api/v1/models/{id}/fine-tune` - Fine-tune model

### AI Enhancement

#### TTS/STT Service (Port 8006)
**Purpose**: Text-to-speech and speech-to-text

**Endpoints**:
- `POST /api/v1/tts` - Text to speech
- `POST /api/v1/stt` - Speech to text

**Models**: Local integration planned

#### Model Fine-tuning (Port 8007)
**Purpose**: LLM fine-tuning

**Endpoints**:
- `POST /api/v1/fine-tune` - Start fine-tuning job
- `GET /api/v1/fine-tune/{id}` - Get job status

#### OpenWebUI (Port 8080)
**Purpose**: Web-based chat interface

**Features**:
- Chat interface
- RAG integration
- Tool calling
- Model selection

### Monitoring

#### Prometheus
**Purpose**: Metrics storage and querying

**Port**: 9090

**Metrics**:
- Service metrics (custom)
- Container metrics (cAdvisor)
- Node metrics (node_exporter)

#### Grafana
**Purpose**: Visualization dashboards

**Port**: 3000

**Dashboards**:
- Service health
- Performance metrics
- Resource usage
- Custom dashboards

#### InfluxDB
**Purpose**: Time-series metrics storage

**Port**: 8086

**Use Cases**:
- Performance metrics
- Custom metrics
- Long-term storage

#### Telegraf
**Purpose**: Metrics collection and aggregation

**Input Plugins**:
- Docker
- System
- PostgreSQL
- Redis

**Output**: InfluxDB, Prometheus

#### Alertmanager
**Purpose**: Alert management and routing

**Port**: 9093

**Integrations**:
- Email (planned)
- Slack (planned)
- PagerDuty (planned)

## Service Dependencies

```
traefik
  ├── authelia
  │   ├── postgres
  │   └── redis
  ├── api-gateway
  │   ├── redis (rate limiting)
  │   └── authelia
  ├── plugin-registry
  │   ├── postgres
  │   └── redis
  ├── marketplace
  │   ├── postgres
  │   ├── redis
  │   └── plugin-registry
  ├── state-manager
  │   ├── postgres
  │   └── redis
  ├── ai-services
  │   ├── qdrant
  │   ├── ollama
  │   └── postgres
  ├── model-management
  │   ├── postgres
  │   └── ollama
  ├── openwebui
  │   ├── postgres
  │   ├── ollama
  │   └── ai-services
  └── monitoring (prometheus, grafana, influxdb, etc.)
```

## Data Flow

### API Request Flow
```
Client → Traefik → Authelia (if auth required) → API Gateway → Service → Database/Cache
```

### AI Query Flow
```
Client → API Gateway → AI Services → Qdrant (search) + Ollama (generate) → Response
```

### Plugin Execution Flow
```
Client → API Gateway → State Manager → Plugin Container → State Update → Response
```

## Scaling Strategies

### Horizontal Scaling
**Stateless services** can be scaled horizontally:
- API Gateway
- Plugin Registry
- Marketplace
- State Manager
- AI Services

**Command**:
```bash
docker compose up -d --scale api-gateway=3
```

### Vertical Scaling
**Stateful services** require vertical scaling:
- PostgreSQL
- Redis
- Qdrant
- Neo4j

**Method**: Adjust resource limits in `docker-compose.yml`

## Service Configuration

### Environment Variables
All services use environment variables for configuration:
- Located in `infrastructure/docker/.env`
- Template in `infrastructure/docker/.env.example`
- Never commit `.env` to git

### Health Checks
All services have health checks:
- Endpoint: `/health`
- Interval: 30s
- Timeout: 10s
- Retries: 3

### Restart Policies
All services use: `restart: unless-stopped`

## Performance Optimization

### Database
- Connection pooling (20 connections)
- Query optimization
- Indexing strategy
- Read replicas (planned)

### Caching
- Redis for session storage
- API response caching
- Query result caching

### Load Balancing
- Traefik load balancing
- Round-robin strategy
- Health check integration

## Security

### Network Segmentation
- External network: Traefik only
- Internal network: All services
- Database isolation: Planned

### Authentication
- JWT for API authentication
- Authelia SSO for web interface
- API keys for external access

### Authorization
- Role-based access control (RBAC)
- User groups
- Access control rules

## Monitoring

### Metrics Collection
- Prometheus: Service metrics
- Telegraf: System metrics
- Custom metrics: Business logic

### Logging
- Structured JSON logs
- Centralized logging (planned)
- Log retention: 30 days

### Alerting
- Service health
- Performance degradation
- Resource exhaustion
- Security events

## Disaster Recovery

### Backup Strategy
- Daily database backups
- Weekly volume snapshots
- Off-site backup (planned)

### Recovery Procedures
- Service restart
- Database restore
- Volume restore
- Full system rebuild

## Future Improvements

### Planned
- [ ] Service mesh (Istio)
- [ ] Event-driven architecture (Kafka)
- [ ] Read replicas for databases
- [ ] CDN for static assets
- [ ] Multi-region deployment

### Under Consideration
- [ ] GraphQL API gateway
- [ ] gRPC for inter-service communication
- [ ] Distributed tracing (Jaeger)
- [ ] Circuit breakers ( resilience)
