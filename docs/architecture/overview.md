# Minder Architecture Documentation

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         Minder Platform                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Minder Kernel                           │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │ │
│  │  │ Module       │  │ Event        │  │ Knowledge    │    │ │
│  │  │ Registry     │  │ Bus         │  │ Graph        │    │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘    │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │ │
│  │  │ Plugin       │  │ Correlation  │  │ Character    │    │ │
│  │  │ Loader       │  │ Engine       │  │ Engine       │    │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                     Module Interface                       │ │
│  │  (BaseModule with register, collect, analyze, train...)    │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│          ┌───────────────────┼───────────────────┐              │
│          ▼                   ▼                   ▼              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐      │
│  │  Fund       │     │  Network    │     │  Weather    │      │
│  │  Module     │     │  Module     │     │  Module     │      │
│  └─────────────┘     └─────────────┘     └─────────────┘      │
│          │                   │                   │              │
│          └───────────────────┼───────────────────┘              │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Data Layer                              │ │
│  │  PostgreSQL │ InfluxDB │ Qdrant │ Redis │ Ollama          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                   Interface Layer                          │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │ │
│  │  │ REST API │  │  Voice   │  │OpenWebUI │  │ Grafana  │  │ │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Minder Kernel

**Responsibilities:**
- Module lifecycle management
- Event routing and handling
- Cross-module communication
- System orchestration

**Key Methods:**
```python
class MinderKernel:
    async def start()                          # Initialize system
    async def stop()                           # Graceful shutdown
    async def run_module_pipeline(module, pipeline)
    async def discover_all_correlations()
    async def query_modules(query)
    async def get_system_status()
```

### 2. Module Registry

**Purpose:** Central registry for all modules

**Features:**
- Dynamic module registration
- Dependency validation
- Initialization ordering (topological sort)
- Health monitoring

**Data Structures:**
```python
{
    'modules': {
        'fund': FundModule,
        'network': NetworkModule,
        ...
    },
    'metadata': {
        'fund': ModuleMetadata,
        'network': ModuleMetadata,
        ...
    },
    'dependency_graph': {
        'network': [],
        'fund': [],
        ...
    }
}
```

### 3. Event Bus

**Purpose:** Pub/Sub messaging for module communication

**Event Types:**
```python
class EventType(Enum):
    MODULE_REGISTERED = "module_registered"
    DATA_COLLECTED = "data_collected"
    ANALYSIS_COMPLETE = "analysis_complete"
    ANOMALY_DETECTED = "anomaly_detected"
    CORRELATION_FOUND = "correlation_found"
    ...
```

**Usage Example:**
```python
# Publish event
await event_bus.publish(Event(
    type=EventType.ANOMALY_DETECTED,
    source="fund",
    data={'fund_code': 'XYZ', 'anomaly': 'price_spike'}
))

# Subscribe to events
await event_bus.subscribe(EventType.ANOMALY_DETECTED, handler)
```

### 4. Knowledge Graph

**Purpose:** Store and query entity relationships

**Entity Types:**
```python
class EntityType(Enum):
    FUND = "fund"
    NETWORK = "network"
    WEATHER = "weather"
    CRYPTO = "crypto"
    NEWS = "news"
    ...
```

**Relation Types:**
```python
class RelationType(Enum):
    CORRELATES = "correlates"
    CAUSES = "causes"
    PRECEDES = "precedes"
    AFFECTS = "affects"
    ...
```

**Query Examples:**
```python
# Find path between entities
path = await kg.find_path(
    source_id='fund:TEK',
    target_id='news:tech_sector',
    max_depth=3
)

# Query by type
entities = await kg.query(
    entity_type=EntityType.FUND,
    attributes={'risk_level': 'high'}
)
```

### 5. Correlation Engine

**Purpose:** Discover relationships between module data

**Correlation Types:**
- **Temporal:** Time-based correlations (e.g., fund returns ↔ network latency)
- **Causal:** Potential cause-effect relationships
- **Semantic:** Vector similarity in Qdrant
- **Statistical:** Pearson/Spearman correlations

**Discovery Process:**
```python
async def discover_correlations(module_a, module_b):
    # 1. Get correlation hints from both modules
    hints_a = await module_a.get_correlations(module_b)
    hints_b = await module_b.get_correlations(module_a)

    # 2. Analyze and score correlations
    correlations = analyze_correlations(hints_a, hints_b)

    # 3. Store in knowledge graph
    for corr in correlations:
        await kg.add_relation(corr)

    return correlations
```

## Module System

### Module Interface

All modules must implement `BaseModule`:

```python
class BaseModule(ABC):
    @abstractmethod
    async def register() -> ModuleMetadata:
        """Register module with kernel"""

    @abstractmethod
    async def collect_data(since=None) -> Dict[str, int]:
        """Fetch/ingest data from sources"""

    @abstractmethod
    async def analyze() -> Dict[str, Any]:
        """Process and analyze collected data"""

    @abstractmethod
    async def train_ai(model_type="default") -> Dict[str, Any]:
        """Train ML models on module data"""

    @abstractmethod
    async def index_knowledge(force=False) -> Dict[str, int]:
        """Create vector embeddings for RAG"""

    @abstractmethod
    async def get_correlations(other_module) -> List[Dict]:
        """Provide correlation hints with other modules"""

    @abstractmethod
    async def get_anomalies(severity, limit) -> List[Dict]:
        """Return detected anomalies"""
```

### Module Lifecycle

```
UNREGISTERED → REGISTERED → INITIALIZING → READY
                                    ↓
                                  ERROR
```

**State Transitions:**
1. **UNREGISTERED**: Module discovered but not registered
2. **REGISTERED**: Module metadata registered with kernel
3. **INITIALIZING**: Module is initializing (connecting to data sources, etc.)
4. **READY**: Module is ready to process requests
5. **ERROR**: Module encountered an error

### Hot Module Loading

```python
# Load new module at runtime
new_module = await plugin_loader.load_module('weather')

# Register with kernel
await kernel.registry.register_module(new_module)

# Initialize
await kernel.registry.initialize_all()

# Now available for queries
results = await kernel.query_modules("What's the weather?")
```

## Data Flow

### 1. Data Collection Flow

```
Module.collect_data()
    ↓
Fetch from source (API, DB, etc.)
    ↓
Transform and validate
    ↓
Store in database
    ↓
Publish DATA_COLLECTED event
    ↓
Update knowledge graph
```

### 2. Analysis Flow

```
Module.analyze()
    ↓
Retrieve data from database
    ↓
Compute metrics/patterns
    ↓
Generate insights
    ↓
Publish ANALYSIS_COMPLETE event
    ↓
Store in knowledge graph
```

### 3. Cross-Module Query Flow

```
User Query (via API/Chat)
    ↓
Kernel.query_modules(query)
    ↓
Distribute to all ready modules
    ↓
Each module.query()
    ↓
Aggregate results
    ↓
Inject character personality
    ↓
Generate response (via Ollama)
    ↓
Return to user
```

## Technology Stack

### Core
- **Language**: Python 3.11
- **Framework**: FastAPI
- **Async**: asyncio, uvloop

### Databases
- **PostgreSQL**: Structured data (fund prices, metadata)
- **InfluxDB**: Time-series data (network metrics, sensor data)
- **Qdrant**: Vector embeddings (RAG knowledge base)
- **Redis**: Caching and session management

### AI/ML
- **Ollama**: Local LLM inference
- **scikit-learn**: Traditional ML models
- **pandas/numpy**: Data processing

### Voice
- **Whisper**: Speech-to-Text
- **Coqui TTS**: Text-to-Speech

### Orchestration
- **Docker**: Containerization
- **Docker Compose**: Service orchestration

## Scalability

### Horizontal Scaling

```yaml
# docker-compose.yml
services:
  minder-api:
    deploy:
      replicas: 3  # Run 3 API instances
```

### Module Isolation

Each module runs in its own process:
```
minder-module-fund:      Container 1
minder-module-network:  Container 2
minder-module-weather:  Container 3
```

### Database Sharding

```
PostgreSQL (fund data)     → Shard by fund_code
InfluxDB (time-series)     → Shard by time range
Qdrant (vectors)           → Shard by collection
```

## Security

### Authentication

```python
# API key authentication
@app.middleware("http")
async def verify_api_key(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not validate_api_key(api_key):
        raise HTTPException(status_code=401)
```

### Authorization

```python
# Role-based access control
class Permission(Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"

def check_permission(user: User, permission: Permission):
    return permission in user.permissions
```

### Data Encryption

- **In transit**: TLS/SSL
- **At rest**: Database encryption
- **Environment variables**: Sensitive config in .env

## Monitoring

### Metrics

```python
# Custom metrics
from prometheus_client import Counter, Histogram

requests_total = Counter('minder_requests_total', 'Total requests')
request_duration = Histogram('minder_request_duration_seconds', 'Request duration')

@app.get("/api/endpoint")
async def endpoint():
    with request_duration.time():
        requests_total.inc()
        # Handle request
```

### Logging

```python
# Structured logging
logger.info(
    "module_pipeline_started",
    extra={
        'module': 'fund',
        'pipeline': ['collect', 'analyze'],
        'user_id': user.id
    }
)
```

### Health Checks

```python
@app.get("/health")
async def health():
    checks = {
        'kernel': kernel.running,
        'database': check_db(),
        'redis': check_redis(),
        'qdrant': check_qdrant()
    }
    return {
        'status': 'healthy' if all(checks.values()) else 'degraded',
        'checks': checks
    }
```

## Performance Optimization

### Caching Strategy

```python
# Redis caching
from functools import lru_cache

@lru_cache(maxsize=1000)
async def get_fund_metadata(fund_code: str):
    # Check cache first
    cached = await redis.get(f"fund:{fund_code}")
    if cached:
        return json.loads(cached)

    # Fetch from database
    metadata = await db.fetch_fund_metadata(fund_code)

    # Store in cache
    await redis.setex(f"fund:{fund_code}", 3600, json.dumps(metadata))

    return metadata
```

### Batch Processing

```python
# Process funds in batches
async def process_funds_batch(fund_codes: List[str], batch_size=50):
    for i in range(0, len(fund_codes), batch_size):
        batch = fund_codes[i:i+batch_size]
        await asyncio.gather(*[
            process_fund(code) for code in batch
        ])
```

### Database Connection Pooling

```python
# Connection pool
from psycopg2 import pool

postgres_pool = pool.SimpleConnectionPool(
    minconn=5,
    maxconn=20,
    host='localhost',
    database='fundmind'
)
```

## Deployment Patterns

### Development

```bash
# Run with hot reload
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
# Run with multiple workers
gunicorn api.main:app \
  -w 4 \
  -k uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### Docker

```bash
# Build and run
docker-compose up -d --scale minder-api=3
```

---

**Document Version:** 1.0.0
**Last Updated:** 2026-04-12
