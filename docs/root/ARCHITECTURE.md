# Minder Architecture Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        MINDER PLATFORM                          │
│                    (Modular RAG System)                          │
└─────────────────────────────────────────────────────────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                │                  │                  │
         ┌────────▼────────┐ ┌────▼──────┐ ┌─────▼─────────┐
         │   API Layer     │ │  Monitor  │ │   Security    │
         │  (FastAPI)      │ │  System   │ │   Middleware  │
         └────────┬────────┘ └────┬──────┘ └─────┬─────────┘
                  │               │              │
         ┌────────▼───────────────▼──────────────▼────────┐
         │              Minder Kernel                     │
         │         (Orchestration Engine)                │
         │  • Plugin Management                          │
         │  • Event Bus                                   │
         │  • Knowledge Graph                            │
         │  • Correlation Engine                         │
         └────────┬───────────────┬───────────────┬────────┘
                  │               │               │
    ┌─────────────┼───────────────┼───────────────┼─────────────┐
    │             │               │               │             │
┌───▼────┐ ┌───▼────┐ ┌────▼────┐ ┌─────▼────┐ ┌────▼────┐
│Weather │ │  News  │ │  Crypto │ │  Network │ │  TEFAS  │
│Plugin  │ │ Plugin │ │ Plugin  │ │ Plugin  │ │ Plugin  │
└───┬────┘ └───┬────┘ └────┬────┘ └─────┬────┘ └────┬────┘
    │          │           │             │           │
    └──────────┴───────────┴─────────────┴───────────┘
                           │
         ┌─────────────────▼─────────────────┐
         │      Plugin Sandbox System       │
         │   • Resource Limits               │
         │   • Memory Constraints           │
         │   • CPU Throttling               │
         │   • Isolated Execution           │
         └─────────────────┬─────────────────┘
                           │
    ┌────────────────────┼────────────────────┐
    │                    │                    │
┌───▼────────┐    ┌─────▼──────┐    ┌───────▼────┐
│ PostgreSQL │    │  InfluxDB  │    │   Qdrant   │
│ (Primary)  │    │ (Metrics)  │    │  (Vectors) │
└────────────┘    └────────────┘    └────────────┘
       │                  │                   │
    ┌──▼──────────────────▼───────────────────▼────┐
    │              Data Storage Layer           │
    │  • Structured Data (PostgreSQL)          │
    │  • Time-Series Metrics (InfluxDB)        │
    │  • Vector Embeddings (Qdrant)             │
    │  • Cache Layer (Redis)                   │
    └──────────────────────────────────────────┘
```

## Component Details

### 1. API Layer (FastAPI)
```
┌────────────────────────────────────────────────────┐
│               API Endpoints                        │
├────────────────────────────────────────────────────┤
│ GET  /health          → Health Check               │
│ GET  /plugins         → List Plugins                │
│ GET  /system/status   → System Status              │
│ POST /auth/login      → Authentication            │
│ POST /plugins/{name}/pipeline → Run Plugin         │
└────────────────────────────────────────────────────┘
```

### 2. Minder Kernel (Core)
```
┌────────────────────────────────────────────────────┐
│              MinderKernel Class                    │
├────────────────────────────────────────────────────┤
│ Responsibilities:                                  │
│ • Plugin Lifecycle Management                     │
│ • Cross-Plugin Communication                     │
│ • Event Bus Management                           │
│ • Knowledge Graph Coordination                   │
│ • Task Scheduling & Execution                    │
└────────────────────────────────────────────────────┘
```

### 3. Plugin Architecture
```
┌────────────────────────────────────────────────────┐
│              BaseModule Interface                 │
├────────────────────────────────────────────────────┤
│ Required Methods:                                 │
│ • register() → Plugin metadata                    │
│                                                    │
│ Optional Methods:                                 │
│ • collect_data() → Gather external data           │
│ • analyze() → Process collected data              │
│ • train_ai() → Train ML models                    │
│ • index_knowledge() → Build knowledge base       │
│ • query() → Search indexed data                   │
└────────────────────────────────────────────────────┘
```

### 4. Plugin Sandbox System
```
┌────────────────────────────────────────────────────┐
│         ThreadSandbox Class                       │
├────────────────────────────────────────────────────┤
│ Security Features:                                │
│ • Memory Limit: 256MB per plugin                 │
│ • CPU Limit: 30% per plugin                      │
│ • Execution Timeout: 120 seconds                 │
│ • Filesystem Access Control                       │
│ • Network Access Restrictions                     │
└────────────────────────────────────────────────────┘
```

### 5. Database Layer
```
┌────────────────────────────────────────────────────┐
│              Data Storage Architecture              │
├────────────────────────────────────────────────────┤
│                                                    │
│  PostgreSQL    → Structured data, user data       │
│  InfluxDB      → Time-series metrics, monitoring  │
│  Qdrant        → Vector embeddings, semantic search│
│  Redis         → Caching, session management       │
│                                                    │
└────────────────────────────────────────────────────┘
```

## Data Flow

### Real Data Collection Flow
```
1. External API Call
   ↓
2. Plugin Data Collection (collect_data)
   ↓
3. Data Validation & Sanitization
   ↓
4. Database Storage (PostgreSQL/InfluxDB/Qdrant)
   ↓
5. Analysis Processing (analyze)
   ↓
6. ML Model Training (train_ai)
   ↓
7. Knowledge Indexing (index_knowledge)
   ↓
8. Query & Retrieval (query)
```

### Real Data Sources
```
WEATHER PLUGIN  → api.weather.gov  → REAL weather data
NEWS PLUGIN    → News API sources → REAL news articles  
CRYPTO PLUGIN  → Binance/Coingecko → REAL crypto prices
NETWORK PLUGIN → System monitoring → REAL network stats
TEFAS PLUGIN   → tefas.gov.tr     → REAL fund data
```

## Security Architecture

```
┌────────────────────────────────────────────────────┐
│              Security Layers                       │
├────────────────────────────────────────────────────┤
│                                                    │
│  1. JWT Authentication                            │
│     → Token-based access control                  │
│                                                    │
│  2. Rate Limiting                                 │
│     → 60 requests/minute per user                 │
│                                                    │
│  3. Input Sanitization                            │
│     → SQL Injection prevention                     │
│     → XSS protection                              │
│     → Command injection blocking                   │
│                                                    │
│  4. Network Detection                             │
│     → Local/VPN/Public network identification      │
│                                                    │
│  5. Plugin Sandboxing                             │
│     → Resource isolation                          │
│     → Permission enforcement                       │
│                                                    │
└────────────────────────────────────────────────────┘
```

## Monitoring Architecture

```
┌────────────────────────────────────────────────────┐
│         Performance Monitoring System               │
├────────────────────────────────────────────────────┤
│                                                    │
│  Real-time Metrics:                               │
│  • CPU Usage (current/average)                    │
│  • Memory Usage (current/available)                │
│  • API Response Times (avg/P95/P99)                │
│  • Database Query Performance                     │
│  • Plugin Execution Metrics                        │
│                                                    │
│  Collection Methods:                              │
│  • psutil system monitoring                      │
│  • API endpoint tracking                          │
│  • Database query logging                         │
│  • Plugin operation timing                        │
│                                                    │
│  Export:                                          │
│  • JSON file exports                              │
│  • CLI monitoring tools                           │
│  • Real-time alerting                             │
│                                                    │
└────────────────────────────────────────────────────┘
```

## Deployment Architecture

```
┌────────────────────────────────────────────────────┐
│          Production Deployment Setup                │
├────────────────────────────────────────────────────┤
│                                                    │
│  Docker Containers:                                │
│  • minder-api (FastAPI application)                │
│  • postgres (Database)                            │
│  • influxdb (Time-series DB)                       │
│  • qdrant (Vector DB)                             │
│  • redis (Cache)                                   │
│  • grafana (Monitoring UI)                         │
│  • prometheus (Metrics collection)                 │
│                                                    │
│  Networking:                                       │
│  • Internal Docker network                         │
│  • Port mappings (8000:API, 3002:Grafana)        │
│  • Health checks on all services                   │
│                                                    │
│  Storage:                                          │
│  • Docker volumes for data persistence             │
│  • Automated backups to /var/backups/minder       │
│  • Log rotation and cleanup                        │
│                                                    │
└────────────────────────────────────────────────────┘
```

## Technology Stack

```
Frontend/API:  FastAPI, Python 3.11+
Databases:     PostgreSQL 16, InfluxDB 2.x, Qdrant, Redis
Monitoring:    Prometheus, Grafana, Custom Python scripts
Security:      JWT, Rate limiting, Input sanitization
Deployment:    Docker, Docker Compose
Testing:       pytest, 117/117 tests passing
```

## Key Features

1. **Modular Plugin Architecture**: Hot-swappable plugins
2. **Real Data Integration**: No mock data, live API connections
3. **Enterprise Security**: Multi-layer security approach
4. **Comprehensive Monitoring**: Real-time performance tracking
5. **Production Ready**: Automated deployment, backups, scaling
6. **Knowledge Graph**: AI-powered data relationships
7. **Event-Driven**: Async event bus for cross-plugin communication
8. **Sandboxed Execution**: Resource-isolated plugin execution

---

**Architecture Version**: 1.0.0  
**Last Updated**: 2026-04-18  
**Status**: Production Ready
