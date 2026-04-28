# Architecture Documentation

Welcome to the Minder Platform architecture documentation. This section covers the system design, components, and technical decisions.

## Overview

Minder Platform is a production-ready microservices platform for AI plugin management, featuring:

- **24 microservices** (21 healthy, 87.5% success rate) - Independent, scalable services
- **Enterprise security** - SSO, 2FA, role-based access control
- **AI capabilities** - RAG pipeline, embeddings, LLM integration
- **Comprehensive monitoring** - Prometheus, Grafana, InfluxDB, Alertmanager

## Architecture Guides

### [System Overview](overview.md)
**Essential** - High-level system architecture.

Covers:
- Platform overview
- Service architecture
- Data flow
- Technology stack
- Design principles

### [Project Structure](project-structure.md)
**Reference** - Complete project structure reference.

Covers:
- Directory layout
- Service structure
- File organization
- Build process
- Development workflow

### [Microservices Architecture](microservices.md)
**In-depth** - Detailed microservices design.

Covers:
- Service communication
- API design
- Data management
- Scaling strategies
- Service discovery

## System Components

### Security Layer (2)
- **Traefik** - Reverse proxy, load balancer, SSL termination
- **Authelia** - SSO, 2FA, access control

### Core Infrastructure (5)
- **PostgreSQL** - Primary database
- **Redis** - Caching, sessions, rate limiting
- **Qdrant** - Vector database for embeddings
- **Ollama** - Local LLM inference
- **Neo4j** - Graph database for dependencies

### Core APIs (6)
- **API Gateway** (8000) - Single entry point
- **Plugin Registry** (8001) - Plugin discovery
- **Marketplace** (8002) - Plugin marketplace
- **State Manager** (8003) - Plugin state tracking
- **AI Services** (8004) - RAG pipeline
- **Model Management** (8005) - Model versioning

### AI Enhancement (3)
- **TTS/STT Service** (8006) - Text-to-speech
- **Model Fine-tuning** (8007) - LLM fine-tuning
- **OpenWebUI** (8080) - Web-based chat interface

### Monitoring (7)
- **Prometheus** (9090) - Metrics storage
- **Grafana** (3000) - Visualization dashboards
- **InfluxDB** (8086) - Time-series metrics
- **Telegraf** - Metrics collection
- **Alertmanager** (9093) - Alert management
- **PostgreSQL Exporter** (9187) - DB metrics
- **Redis Exporter** (9121) - Cache metrics

## Architecture Diagram

```
                      Internet
                         │
                    ┌────▼─────┐
                    │  Traefik │ (Port 80/443)
                    └────┬─────┘
                         │
              ┌──────────┴──────────┐
              │                     │
         ┌────▼────┐          ┌────▼────┐
         │Authelia │          │   API   │
         │   SSO   │          │ Gateway │
         └─────────┘          └────┬────┘
                                   │
              ┌──────────────────────┼──────────────────┐
              │                      │                  │
         ┌────▼────┐           ┌─────▼─────┐      ┌────▼────┐
         │Plugin   │           │Market     │      │  State  │
         │Registry │           │place      │      │Manager  │
         └─────────┘           └───────────┘      └─────────┘
              │                      │                  │
              └──────────────────────┼──────────────────┘
                                     │
                             ┌───────▼────────┐
                             │  AI Services   │
                             └────────────────┘
                                     │
              ┌──────────────────────┼──────────────────┐
              │                      │                  │
         ┌────▼────┐           ┌─────▼─────┐      ┌────▼────┐
         │Postgres │           │  Redis    │      │ Qdrant  │
         │         │           │           │      │         │
         └─────────┘           └───────────┘      └─────────┘
```

## Key Design Principles

### 1. Microservices Architecture
- **Independent** - Deploy, scale, update separately
- **Specialized** - Focused on specific domain
- **Replaceable** - Swap without affecting others
- **Observable** - Built-in health checks and metrics

### 2. API-First Design
- RESTful API endpoints
- OpenAPI/Swagger documentation
- Health check endpoints
- Structured logging

### 3. Security First
- SSO with Authelia
- 2FA (TOTP, WebAuthn)
- Role-based access control
- Rate limiting
- Input validation

### 4. Observability
- Health checks on all services
- Structured logging (JSON format)
- Prometheus-compatible metrics
- Request ID tracking

### 5. Configuration Management
- Environment-based configuration
- Secrets in `.env` (gitignored)
- Default values in `.env.example`
- Validation with Pydantic

## Technology Stack

### Backend
- **Python 3.11+** - Core runtime
- **FastAPI** - API framework
- **Pydantic** - Data validation
- **SQLAlchemy** - ORM

### Infrastructure
- **Docker** - Container runtime
- **Docker Compose** - Orchestration
- **Traefik** - Reverse proxy
- **Authelia** - Authentication

### Data Stores
- **PostgreSQL 16** - Primary database
- **Redis 7** - Cache and sessions
- **Qdrant** - Vector database
- **Neo4j** - Graph database

### Monitoring
- **Prometheus** - Metrics storage
- **Grafana** - Visualization
- **InfluxDB** - Time-series data
- **Telegraf** - Metrics collection

## Additional Resources

- [API Reference](../api/reference.md) - Complete API documentation
- [Development Guide](../development/development.md) - Development workflow
- [Deployment Guide](../deployment/production.md) - Production setup

## Contributing to Architecture

Have architectural improvements?

1. Review existing architecture
2. Propose changes in GitHub Issues
3. Discuss with team
4. Submit RFC (Request for Comments)
5. Implement with tests
