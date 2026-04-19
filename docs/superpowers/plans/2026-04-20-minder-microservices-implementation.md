# Minder Microservices Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Minder from monolithic FastAPI application to domain-driven microservices architecture with plugin deployment capabilities

**Architecture:** Separate business domains into independent Docker containers (Gateway, Auth, Plugins, Data Collection, Analysis) communicating via HTTP, Redis Pub/Sub, and message queues

**Tech Stack:** FastAPI, Docker Compose, PostgreSQL (schemas), InfluxDB, Qdrant, Redis, Prometheus/Grafana

---

## Phase 1: Preparation (1-2 days)

### Task 1.1: Create Shared Library Structure

**Files:**
- Create: `shared/__init__.py`
- Create: `shared/models/__init__.py`
- Create: `shared/models/common.py`
- Create: `shared/utils/__init__.py`
- Create: `shared/utils/logging.py`
- Create: `shared/config/__init__.py`
- Create: `shared/config/base.py`
- Create: `shared/database/__init__.py`
- Create: `shared/database/postgres.py`
- Create: `shared/database/redis.py`

- [ ] **Step 1: Create shared directory structure**

```bash
mkdir -p /root/minder/shared/{models,utils,config,database}
touch /root/minder/shared/__init__.py
touch /root/minder/shared/models/__init__.py
touch /root/minder/shared/utils/__init__.py
touch /root/minder/shared/config/__init__.py
touch /root/minder/shared/database/__init__.py
```

- [ ] **Step 2: Create common Pydantic models**

```python
# shared/models/common.py
from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime
from enum import Enum

class ServiceStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"

class HealthResponse(BaseModel):
    service: str
    status: ServiceStatus
    timestamp: datetime = Field(default_factory=datetime.now)
    uptime_seconds: float
    details: Optional[Dict[str, Any]] = None

class PluginManifest(BaseModel):
    name: str
    version: str
    description: str
    author: str
    requires: list[str] = []
    container: Optional[Dict[str, Any]] = None

class ServiceMessage(BaseModel):
    type: str
    source: str
    data: Dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.now)
```

- [ ] **Step 3: Create shared logging utilities**

```python
# shared/utils/logging.py
import logging
import sys
from typing import Optional

def setup_logger(
    name: str,
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """Setup standardized logger for services"""
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
```

- [ ] **Step 4: Create shared config base**

```python
# shared/config/base.py
from pathlib import Path
from typing import Optional, Dict, Any
import yaml
import os

class BaseConfig:
    """Base configuration class for all services"""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path("/app/config.yaml")
        self.config_data: Dict[str, Any] = {}
        if self.config_path.exists():
            self._load_config()

    def _load_config(self):
        """Load YAML configuration"""
        with open(self.config_path) as f:
            self.config_data = yaml.safe_load(f) or {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value with env override"""
        # Check environment variable first
        env_key = key.upper().replace('.', '_')
        if env_key in os.environ:
            return os.environ[env_key]

        # Check config file
        keys = key.split('.')
        value = self.config_data
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
        return value if value is not None else default

    @property
    def postgres_url(self) -> str:
        """Get PostgreSQL connection URL"""
        host = self.get('database.host', 'postgres')
        port = self.get('database.port', 5432)
        user = self.get('database.user', 'postgres')
        password = self.get('database.password', 'postgres')
        return f"postgresql://{user}:{password}@{host}:{port}"

    @property
    def redis_url(self) -> str:
        """Get Redis connection URL"""
        host = self.get('redis.host', 'redis')
        port = self.get('redis.port', 6379)
        return f"redis://{host}:{port}"
```

- [ ] **Step 5: Create PostgreSQL database helper**

```python
# shared/database/postgres.py
import asyncpg
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)

class PostgresHelper:
    """PostgreSQL database helper for services"""

    def __init__(self, dsn: str, schema: str = "public"):
        self.dsn = dsn
        self.schema = schema
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool"""
        self.pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
            command_timeout=60
        )
        logger.info(f"Connected to PostgreSQL, schema: {self.schema}")

    async def disconnect(self):
        """Close connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Disconnected from PostgreSQL")

    async def execute(
        self,
        query: str,
        *args,
        fetch: str = "all"
    ) -> Any:
        """Execute SQL query"""
        async with self.pool.acquire() as conn:
            statement = await conn.prepare(query)
            if fetch == "one":
                return await statement.fetchrow(*args)
            elif fetch == "val":
                return await statement.fetchval(*args)
            else:
                return await statement.fetch(*args)

    async def init_schema(self):
        """Initialize service schema"""
        async with self.pool.acquire() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            logger.info(f"Schema {self.schema} initialized")
```

- [ ] **Step 6: Create Redis helper**

```python
# shared/database/redis.py
import aioredis
from typing import Optional, Any, Dict
import json
import logging

logger = logging.getLogger(__name__)

class RedisHelper:
    """Redis helper for caching and pub/sub"""

    def __init__(self, url: str, db: int = 0):
        self.url = url
        self.db = db
        self.client: Optional[aioredis.Redis] = None

    async def connect(self):
        """Connect to Redis"""
        self.client = await aioredis.from_url(
            f"{url}/{self.db}",
            encoding="utf-8",
            decode_responses=True
        )
        logger.info(f"Connected to Redis, db: {self.db}")

    async def disconnect(self):
        """Disconnect from Redis"""
        if self.client:
            await self.client.close()
            logger.info("Disconnected from Redis")

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        value = await self.client.get(key)
        if value:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = 3600
    ):
        """Set value in cache with TTL"""
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        await self.client.setex(key, ttl, value)

    async def publish(self, channel: str, message: Dict[str, Any]):
        """Publish message to channel"""
        await self.client.publish(channel, json.dumps(message))

    async def subscribe(self, channel: str):
        """Subscribe to channel"""
        pubsub = self.client.pubsub()
        await pubsub.subscribe(channel)
        return pubsub
```

- [ ] **Step 7: Commit shared library**

```bash
git add shared/
git commit -m "feat(microservices): create shared library with common models, config, and database helpers"
```

### Task 1.2: Create Service Templates

**Files:**
- Create: `services/template/Dockerfile`
- Create: `services/template/main.py`
- Create: `services/template/requirements.txt`
- Create: `services/template/config.yaml`

- [ ] **Step 1: Create services directory and template**

```bash
mkdir -p /root/minder/services/template
```

- [ ] **Step 2: Create service Dockerfile template**

```dockerfile
# services/template/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-cache-dir --no-install-recommends \
    curl \
    postgresql-client \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:${SERVICE_PORT:-8000}/health || exit 1

# Run service
CMD ["python", "main.py"]
```

- [ ] **Step 3: Create service main.py template**

```python
# services/template/main.py
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
import asyncio
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.postgres import PostgresHelper
from shared.database.redis import RedisHelper

# Configuration
SERVICE_NAME = os.getenv("SERVICE_NAME", "template-service")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

# Initialize FastAPI
app = FastAPI(
    title=SERVICE_NAME.replace("-", " ").title(),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Database connections (will be initialized on startup)
postgres: PostgresHelper = None
redis: RedisHelper = None

@app.on_event("startup")
async def startup():
    """Initialize service connections"""
    global postgres, redis

    logger.info(f"Starting {SERVICE_NAME}...")

    # Connect to PostgreSQL
    postgres = PostgresHelper(
        dsn=config.postgres_url,
        schema=os.getenv("DB_SCHEMA", "public")
    )
    await postgres.connect()
    await postgres.init_schema()

    # Connect to Redis
    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    logger.info(f"{SERVICE_NAME} started successfully")

@app.on_event("shutdown")
async def shutdown():
    """Cleanup service connections"""
    global postgres, redis

    logger.info(f"Shutting down {SERVICE_NAME}...")

    if postgres:
        await postgres.disconnect()

    if redis:
        await redis.disconnect()

    logger.info(f"{SERVICE_NAME} shutdown complete")

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0,  # TODO: implement uptime tracking
        details={"version": "1.0.0"}
    )

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": SERVICE_NAME,
        "status": "running",
        "docs": "/docs"
    }

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=os.getenv("ENVIRONMENT") == "development",
        log_level="info"
    )
```

- [ ] **Step 4: Create service requirements.txt template**

```text
# services/template/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
pydantic-settings==2.1.0
asyncpg==0.29.0
aioredis==2.0.1
python-multipart==0.0.6
pyyaml==6.0.1
```

- [ ] **Step 5: Create service config.yaml template**

```yaml
# services/template/config.yaml
database:
  host: postgres
  port: 5432
  user: postgres
  password: ${POSTGRES_PASSWORD}
  dbname: minder

redis:
  host: redis
  port: 6379

service:
  name: template-service
  port: 8000
  log_level: INFO
```

- [ ] **Step 6: Commit service template**

```bash
git add services/template/
git commit -m "feat(microservices): create service template with Dockerfile, main.py, and config"
```

### Task 1.3: Setup PostgreSQL Schemas

**Files:**
- Create: `migrations/schemas/001_init_schemas.sql`

- [ ] **Step 1: Create schema migration directory**

```bash
mkdir -p /root/minder/migrations/schemas
```

- [ ] **Step 2: Create schema initialization SQL**

```sql
-- migrations/schemas/001_init_schemas.sql

-- Auth schema
CREATE SCHEMA IF NOT EXISTS auth_schema;

-- Plugin schema
CREATE SCHEMA IF NOT EXISTS plugin_schema;

-- Correlation schema
CREATE SCHEMA IF NOT EXISTS correlation_schema;

-- Auth tables
CREATE TABLE IF NOT EXISTS auth_schema.users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(255) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS auth_schema.sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES auth_schema.users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) UNIQUE NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Plugin tables
CREATE TABLE IF NOT EXISTS plugin_schema.plugins (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    version VARCHAR(50) NOT NULL,
    description TEXT,
    author VARCHAR(255),
    enabled BOOLEAN DEFAULT TRUE,
    config JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plugin_schema.plugin_health (
    id SERIAL PRIMARY KEY,
    plugin_name VARCHAR(255) REFERENCES plugin_schema.plugins(name) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    uptime_seconds FLOAT
);

-- Correlation tables
CREATE TABLE IF NOT EXISTS correlation_schema.results (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) NOT NULL,
    correlation_type VARCHAR(100) NOT NULL,
    source_1 VARCHAR(255),
    source_2 VARCHAR(255),
    correlation_value FLOAT,
    p_value FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB
);

CREATE TABLE IF NOT EXISTS correlation_schema.analysis_jobs (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(255) UNIQUE NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    config JSONB,
    result_count INTEGER DEFAULT 0
);

-- Indexes for performance
CREATE INDEX idx_sessions_token ON auth_schema.sessions(token_hash);
CREATE INDEX idx_sessions_expires ON auth_schema.sessions(expires_at);
CREATE INDEX idx_plugin_health_name ON plugin_schema.plugin_health(plugin_name);
CREATE INDEX idx_correlation_results_type ON correlation_schema.results(correlation_type);
CREATE INDEX idx_correlation_results_timestamp ON correlation_schema.results(timestamp);
```

- [ ] **Step 3: Apply schema migration**

```bash
docker-compose exec postgres psql -U postgres -d minder -f /docker-entrypoint-initdb.d/init-schemas.sql
```

Or run directly:
```bash
PGPASSWORD=${POSTGRES_PASSWORD:-postgres} psql -h localhost -U postgres -d minder < migrations/schemas/001_init_schemas.sql
```

- [ ] **Step 4: Commit schema migration**

```bash
git add migrations/schemas/
git commit -m "feat(microservices): add PostgreSQL schema initialization for auth, plugins, and correlation"
```

### Task 1.4: Create Docker Compose Files

**Files:**
- Create: `docker-compose.services.yml`
- Create: `docker-compose.plugins.yml`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Extract business services to separate compose file**

```yaml
# docker-compose.services.yml
version: '3.8'

services:
  # API Gateway
  minder-gateway:
    build:
      context: ./services/gateway
      dockerfile: Dockerfile
    image: minder-gateway:latest
    container_name: minder-gateway
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - SERVICE_NAME=minder-gateway
      - SERVICE_PORT=8000
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - ENVIRONMENT=production
    volumes:
      - ./logs:/var/log/minder
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      minder-auth:
        condition: service_healthy
      minder-plugins:
        condition: service_healthy
      minder-data:
        condition: service_healthy
      minder-analysis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Auth Service
  minder-auth:
    build:
      context: ./services/auth
      dockerfile: Dockerfile
    image: minder-auth:latest
    container_name: minder-auth
    restart: unless-stopped
    ports:
      - "8004:8004"
    environment:
      - SERVICE_NAME=minder-auth
      - SERVICE_PORT=8004
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - DB_SCHEMA=auth_schema
    volumes:
      - ./logs:/var/log/minder
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8004/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Plugin Service
  minder-plugins:
    build:
      context: ./services/plugins
      dockerfile: Dockerfile
    image: minder-plugins:latest
    container_name: minder-plugins
    restart: unless-stopped
    ports:
      - "8001:8001"
    environment:
      - SERVICE_NAME=minder-plugins
      - SERVICE_PORT=8001
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - DB_SCHEMA=plugin_schema
    volumes:
      - ./logs:/var/log/minder
      - ./plugins:/app/plugins:ro
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Data Collection Service
  minder-data:
    build:
      context: ./services/data-collector
      dockerfile: Dockerfile
    image: minder-data:latest
    container_name: minder-data
    restart: unless-stopped
    ports:
      - "8002:8002"
    environment:
      - SERVICE_NAME=minder-data
      - SERVICE_PORT=8002
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - INFLUXDB_INIT_PASSWORD=${INFLUXDB_INIT_PASSWORD:-minder123}
    volumes:
      - ./logs:/var/log/minder
      - ./plugins:/app/plugins:ro
    depends_on:
      postgres:
        condition: service_healthy
      influxdb:
        condition: service_started
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8002/health"]
      interval: 30s
      timeout: 5s
      retries: 3

  # Analysis Service
  minder-analysis:
    build:
      context: ./services/analysis
      dockerfile: Dockerfile
    image: minder-analysis:latest
    container_name: minder-analysis
    restart: unless-stopped
    ports:
      - "8003:8003"
    environment:
      - SERVICE_NAME=minder-analysis
      - SERVICE_PORT=8003
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - DB_SCHEMA=correlation_schema
    volumes:
      - ./logs:/var/log/minder
    depends_on:
      postgres:
        condition: service_healthy
      qdrant:
        condition: service_started
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8003/health"]
      interval: 30s
      timeout: 5s
      retries: 3
```

- [ ] **Step 2: Create plugin services compose file**

```yaml
# docker-compose.plugins.yml
version: '3.8'

services:
  # TEFAS Plugin (example with custom container)
  tefas-plugin:
    build:
      context: ./plugins/tefas
      dockerfile: Dockerfile
    image: tefas-plugin:latest
    container_name: tefas-plugin
    restart: unless-stopped
    ports:
      - "8005:8005"
    environment:
      - PLUGIN_NAME=tefas
      - PLUGIN_PORT=8005
      - DB_HOST=postgres
      - INFLUX_HOST=influxdb
    depends_on:
      postgres:
        condition: service_healthy
      influxdb:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8005/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    profiles:
      - plugins

  # News Plugin (example with custom container)
  news-plugin:
    build:
      context: ./plugins/news
      dockerfile: Dockerfile
    image: news-plugin:latest
    container_name: news-plugin
    restart: unless-stopped
    ports:
      - "8006:8006"
    environment:
      - PLUGIN_NAME=news
      - PLUGIN_PORT=8006
      - DB_HOST=postgres
    depends_on:
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8006/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    profiles:
      - plugins
```

- [ ] **Step 3: Update main docker-compose.yml to remove old minder-api service**

```bash
# Edit docker-compose.yml, remove the old minder-api service definition
# Keep only infrastructure services (postgres, influxdb, qdrant, redis, prometheus, grafana, alertmanager)
```

- [ ] **Step 4: Commit Docker Compose restructure**

```bash
git add docker-compose.yml docker-compose.services.yml docker-compose.plugins.yml
git commit -m "feat(microservices): split docker-compose into infrastructure, services, and plugins files"
```

---

## Phase 2: Auth Service Separation (1 day)

### Task 2.1: Create Auth Service

**Files:**
- Create: `services/auth/main.py`
- Create: `services/auth/Dockerfile`
- Create: `services/auth/requirements.txt`
- Create: `services/auth/config.yaml`
- Move: `api/auth.py` → `services/auth/auth_logic.py`
- Move: `api/auth_endpoints/*` → `services/auth/endpoints/`

- [ ] **Step 1: Create auth service directory**

```bash
mkdir -p /root/minder/services/auth/endpoints
```

- [ ] **Step 2: Move auth logic files**

```bash
# Copy existing auth files to new service
cp /root/minder/api/auth.py /root/minder/services/auth/auth_logic.py
cp -r /root/minder/api/auth_endpoints/* /root/minder/services/auth/endpoints/
```

- [ ] **Step 3: Create auth service main.py**

```python
# services/auth/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.postgres import PostgresHelper
from shared.database.redis import RedisHelper
from endpoints import register, login, logout, verify

SERVICE_NAME = "minder-auth"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8004"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

app = FastAPI(
    title="Minder Auth Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connections
postgres: PostgresHelper = None
redis: RedisHelper = None

@app.on_event("startup")
async def startup():
    global postgres, redis
    logger.info(f"Starting {SERVICE_NAME}...")

    postgres = PostgresHelper(
        dsn=config.postgres_url,
        schema="auth_schema"
    )
    await postgres.connect()
    await postgres.init_schema()

    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    logger.info(f"{SERVICE_NAME} started successfully")

@app.on_event("shutdown")
async def shutdown():
    global postgres, redis
    logger.info(f"Shutting down {SERVICE_NAME}...")
    if postgres:
        await postgres.disconnect()
    if redis:
        await redis.disconnect()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0
    )

# Include auth routers
app.include_router(register.router, prefix="/auth", tags=["auth"])
app.include_router(login.router, prefix="/auth", tags=["auth"])
app.include_router(logout.router, prefix="/auth", tags=["auth"])
app.include_router(verify.router, prefix="/auth", tags=["auth"])

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=False
    )
```

- [ ] **Step 4: Create auth service Dockerfile**

```dockerfile
# services/auth/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:8004/health || exit 1

CMD ["python", "main.py"]
```

- [ ] **Step 5: Create auth service requirements.txt**

```text
# services/auth/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
asyncpg==0.29.0
aioredis==2.0.1
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
python-multipart==0.0.6
pyyaml==6.0.1
```

- [ ] **Step 6: Update auth endpoints to use shared models**

```python
# services/auth/endpoints/register.py
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
import asyncpg
from shared.database.postgres import PostgresHelper
from passlib.context import CryptContext

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Dependency to get postgres connection
async def get_postgres():
    # This will be injected by main.py
    pass

class UserRegister(BaseModel):
    username: str
    email: EmailStr
    password: str

@router.post("/register")
async def register_user(
    user: UserRegister,
    postgres: PostgresHelper = Depends(get_postgres)
):
    """Register new user"""
    # Check if user exists
    existing = await postgres.execute(
        "SELECT id FROM auth_schema.users WHERE username = $1 OR email = $2",
        user.username,
        user.email,
        fetch="one"
    )

    if existing:
        raise HTTPException(status_code=400, detail="User already exists")

    # Hash password
    password_hash = pwd_context.hash(user.password)

    # Create user
    user_id = await postgres.execute(
        """INSERT INTO auth_schema.users (username, email, password_hash)
           VALUES ($1, $2, $3) RETURNING id""",
        user.username,
        user.email,
        password_hash,
        fetch="val"
    )

    return {"user_id": user_id, "message": "User created successfully"}
```

- [ ] **Step 7: Test auth service locally**

```bash
cd /root/minder/services/auth
docker build -t minder-auth:latest .
docker run -p 8004:8004 --env-file ../../.env minder-auth:latest
```

Test health endpoint:
```bash
curl http://localhost:8004/health
```

- [ ] **Step 8: Commit auth service**

```bash
git add services/auth/
git commit -m "feat(microservices): create auth service with user registration, login, logout, and token verification"
```

### Task 2.2: Create API Gateway

**Files:**
- Create: `services/gateway/main.py`
- Create: `services/gateway/Dockerfile`
- Create: `services/gateway/requirements.txt`
- Create: `services/gateway/middleware.py`
- Create: `services/gateway/routing.py`

- [ ] **Step 1: Create gateway service directory**

```bash
mkdir -p /root/minder/services/gateway
```

- [ ] **Step 2: Create gateway routing logic**

```python
# services/gateway/routing.py
from fastapi import Request, HTTPException
from httpx import AsyncClient
import os
from typing import Dict

# Service URLs
SERVICES = {
    "auth": os.getenv("AUTH_SERVICE_URL", "http://minder-auth:8004"),
    "plugins": os.getenv("PLUGIN_SERVICE_URL", "http://minder-plugins:8001"),
    "data": os.getenv("DATA_SERVICE_URL", "http://minder-data:8002"),
    "analysis": os.getenv("ANALYSIS_SERVICE_URL", "http://minder-analysis:8003"),
}

class ServiceRouter:
    """Route requests to appropriate microservice"""

    def __init__(self):
        self.client = AsyncClient(timeout=30.0)

    async def route_request(self, request: Request, service: str, path: str):
        """Forward request to service"""
        if service not in SERVICES:
            raise HTTPException(status_code=404, detail=f"Service {service} not found")

        service_url = SERVICES[service]
        url = f"{service_url}{path}"

        # Forward request
        body = await request.body()

        response = await self.client.request(
            method=request.method,
            url=url,
            headers=dict(request.headers),
            content=body,
            params=request.query_params
        )

        return response

router = ServiceRouter()
```

- [ ] **Step 3: Create gateway middleware**

```python
# services/gateway/middleware.py
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging

logger = logging.getLogger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests and responses"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # Log request
        logger.info(f"Request: {request.method} {request.url.path}")

        # Process request
        response = await call_next(request)

        # Log response
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        logger.info(
            f"Response: {response.status_code} "
            f"({process_time:.3f}s)"
        )

        return response

class AuthMiddleware(BaseHTTPMiddleware):
    """Validate JWT tokens for protected routes"""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health and public endpoints
        if request.url.path in ["/health", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)

        if request.url.path.startswith("/api/auth/"):
            return await call_next(request)

        # Validate token for other routes
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return Response(
                '{"detail": "Not authenticated"}',
                status_code=401,
                media_type="application/json"
            )

        # Token validation logic here
        # For now, just pass through
        return await call_next(request)
```

- [ ] **Step 4: Create gateway main.py**

```python
# services/gateway/main.py
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import uvicorn
import os
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.redis import RedisHelper
from middleware import LoggingMiddleware, AuthMiddleware
from routing import router

SERVICE_NAME = "minder-gateway"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

app = FastAPI(
    title="Minder API Gateway",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add middleware
app.add_middleware(LoggingMiddleware)
app.add_middleware(AuthMiddleware)

# Redis for caching
redis: RedisHelper = None

@app.on_event("startup")
async def startup():
    global redis
    logger.info(f"Starting {SERVICE_NAME}...")

    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    logger.info(f"{SERVICE_NAME} started successfully")

@app.on_event("shutdown")
async def shutdown():
    global redis
    logger.info(f"Shutting down {SERVICE_NAME}...")
    if redis:
        await redis.disconnect()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0
    )

# Route endpoints to services
@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy_request(service: str, path: str, request: Request):
    """Proxy request to appropriate service"""
    try:
        response = await router.route_request(request, service, f"/{path}")
        return JSONResponse(
            content=response.json(),
            status_code=response.status_code
        )
    except Exception as e:
        logger.error(f"Error proxying request: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=False
    )
```

- [ ] **Step 5: Create gateway Dockerfile and requirements**

```dockerfile
# services/gateway/Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "main.py"]
```

```text
# services/gateway/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
httpx==0.26.0
pydantic==2.5.3
aioredis==2.0.1
pyyaml==6.0.1
```

- [ ] **Step 6: Commit API gateway**

```bash
git add services/gateway/
git commit -m "feat(microservices): create API gateway with routing, logging, and auth middleware"
```

---

## Phase 3: Plugin Service Separation (1-2 days)

### Task 3.1: Create Plugin Service

**Files:**
- Create: `services/plugin/main.py`
- Move: `core/plugin_*.py` → `services/plugin/core/`
- Move: `api/plugin_store.py` → `services/plugin/endpoints/`

- [ ] **Step 1: Create plugin service directory structure**

```bash
mkdir -p /root/minder/services/plugin/{core,endpoints}
```

- [ ] **Step 2: Move plugin core files**

```bash
cp /root/minder/core/plugin_loader.py /root/minder/services/plugin/core/
cp /root/minder/core/plugin_hot_reload.py /root/minder/services/plugin/core/
cp /root/minder/core/plugin_manifest.py /root/minder/services/plugin/core/
cp /root/minder/core/plugin_observability.py /root/minder/services/plugin/core/
cp /root/minder/core/plugin_sandbox.py /root/minder/services/plugin/core/
cp /root/minder/core/module_interface_v2.py /root/minder/services/plugin/core/
```

- [ ] **Step 3: Create plugin service main.py**

```python
# services/plugin/main.py
from fastapi import FastAPI
import uvicorn
import os
from pathlib import Path
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.postgres import PostgresHelper
from shared.database.redis import RedisHelper
from core.plugin_loader import PluginLoader
from core.plugin_hot_reload import PluginHotReload
from core.plugin_observability import PluginMetrics, PluginHealthMonitor

SERVICE_NAME = "minder-plugins"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
PLUGINS_PATH = Path(os.getenv("PLUGINS_PATH", "/app/plugins"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

app = FastAPI(
    title="Minder Plugin Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Plugin components
loader: PluginLoader = None
hot_reload: PluginHotReload = None
metrics: PluginMetrics = None
health_monitor: PluginHealthMonitor = None

# Database connections
postgres: PostgresHelper = None
redis: RedisHelper = None

@app.on_event("startup")
async def startup():
    global loader, hot_reload, metrics, health_monitor, postgres, redis

    logger.info(f"Starting {SERVICE_NAME}...")

    # Connect to databases
    postgres = PostgresHelper(
        dsn=config.postgres_url,
        schema="plugin_schema"
    )
    await postgres.connect()
    await postgres.init_schema()

    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    # Initialize plugin system
    loader = PluginLoader({"plugins_path": PLUGINS_PATH})
    await loader.load_all()

    hot_reload = PluginHotReload(loader, PLUGINS_PATH)
    await hot_reload.start()

    metrics = PluginMetrics()
    health_monitor = PluginHealthMonitor(metrics)

    logger.info(f"{SERVICE_NAME} started with {len(loader.plugins)} plugins")

@app.on_event("shutdown")
async def shutdown():
    global hot_reload, postgres, redis

    logger.info(f"Shutting down {SERVICE_NAME}...")

    if hot_reload:
        await hot_reload.stop()

    if postgres:
        await postgres.disconnect()

    if redis:
        await redis.disconnect()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0,
        details={"plugins_loaded": len(loader.plugins) if loader else 0}
    )

# Plugin endpoints will be included here
# from endpoints import plugins, store
# app.include_router(plugins.router)
# app.include_router(store.router)

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=False
    )
```

- [ ] **Step 4: Update plugin core files to use shared library**

Update imports in all plugin core files to use shared models and database helpers.

- [ ] **Step 5: Create plugin service Dockerfile**

```dockerfile
# services/plugin/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for plugins
RUN apt-get update && apt-get install -y --no-cache-dir --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["python", "main.py"]
```

- [ ] **Step 6: Create plugin service requirements.txt**

```text
# services/plugin/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
asyncpg==0.29.0
aioredis==2.0.1
psutil==5.9.8
prometheus-client==0.19.0
pyyaml==6.0.1
python-multipart==0.0.6
```

- [ ] **Step 7: Test plugin service**

```bash
cd /root/minder/services/plugin
docker build -t minder-plugins:latest .
docker run -p 8001:8001 --env-file ../../.env -v ../../plugins:/app/plugins:ro minder-plugins:latest
```

Test health endpoint:
```bash
curl http://localhost:8001/health
```

- [ ] **Step 8: Commit plugin service**

```bash
git add services/plugin/
git commit -m "feat(microservices): create plugin service with loader, hot reload, and observability"
```

---

## Phase 4: Data Collection Service Separation (2 days)

### Task 4.1: Create Data Collection Service

**Files:**
- Create: `services/data-collector/main.py`
- Move: `plugins/tefas/`, `plugins/news/`, `plugins/weather/`, `plugins/crypto/` → Keep in plugins/ but mount into service
- Create: `services/data-collector/scheduler.py`

- [ ] **Step 1: Create data collector service directory**

```bash
mkdir -p /root/minder/services/data-collector
```

- [ ] **Step 2: Create data collector main.py**

```python
# services/data-collector/main.py
from fastapi import FastAPI, BackgroundTasks
import uvicorn
import os
from pathlib import Path
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.postgres import PostgresHelper
from shared.database.redis import RedisHelper
from core.plugin_loader import PluginLoader
from scheduler import DataCollectionScheduler

SERVICE_NAME = "minder-data"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8002"))
PLUGINS_PATH = Path(os.getenv("PLUGINS_PATH", "/app/plugins"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

app = FastAPI(
    title="Minder Data Collection Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Components
loader: PluginLoader = None
scheduler: DataCollectionScheduler = None

# Database connections
postgres: PostgresHelper = None
redis: RedisHelper = None

@app.on_event("startup")
async def startup():
    global loader, scheduler, postgres, redis

    logger.info(f"Starting {SERVICE_NAME}...")

    # Connect to databases
    postgres = PostgresHelper(
        dsn=config.postgres_url,
        schema="public"
    )
    await postgres.connect()

    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    # Initialize plugin loader
    loader = PluginLoader({"plugins_path": PLUGINS_PATH})

    # Load data collection plugins
    data_plugins = ["tefas", "news", "weather", "crypto"]
    for plugin_name in data_plugins:
        await loader.load_plugin(plugin_name)

    # Initialize scheduler
    scheduler = DataCollectionScheduler(loader, redis)
    await scheduler.start()

    logger.info(f"{SERVICE_NAME} started with {len(loader.plugins)} data plugins")

@app.on_event("shutdown")
async def shutdown():
    global scheduler, postgres, redis

    logger.info(f"Shutting down {SERVICE_NAME}...")

    if scheduler:
        await scheduler.stop()

    if postgres:
        await postgres.disconnect()

    if redis:
        await redis.disconnect()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0,
        details={
            "plugins_loaded": len(loader.plugins) if loader else 0,
            "scheduler_running": scheduler.is_running if scheduler else False
        }
    )

@app.post("/collect/{plugin_name}")
async def trigger_collection(plugin_name: str, background_tasks: BackgroundTasks):
    """Manually trigger data collection for a plugin"""
    if not loader or plugin_name not in loader.plugins:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

    background_tasks.add_task(scheduler.collect_data, plugin_name)

    return {"message": f"Data collection triggered for {plugin_name}"}

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=False
    )
```

- [ ] **Step 3: Create data collection scheduler**

```python
# services/data-collector/scheduler.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from core.plugin_loader import PluginLoader
from shared.database.redis import RedisHelper

logger = logging.getLogger(__name__)

class DataCollectionScheduler:
    """Schedule and execute data collection jobs"""

    def __init__(self, loader: PluginLoader, redis: RedisHelper):
        self.loader = loader
        self.redis = redis
        self.is_running = False
        self.tasks: Dict[str, asyncio.Task] = {}

        # Collection schedules (plugin_name -> cron_expression)
        self.schedules = {
            "tefas": "0 */6 * * *",  # Every 6 hours
            "news": "0 */1 * * *",   # Every hour
            "weather": "0 */2 * * *", # Every 2 hours
            "crypto": "*/15 * * * *", # Every 15 minutes
        }

    async def start(self):
        """Start scheduler"""
        self.is_running = True

        # Start collection tasks for each plugin
        for plugin_name in self.schedules:
            task = asyncio.create_task(self._schedule_plugin(plugin_name))
            self.tasks[plugin_name] = task

        logger.info(f"Scheduler started with {len(self.tasks)} tasks")

    async def stop(self):
        """Stop scheduler"""
        self.is_running = False

        # Cancel all tasks
        for task in self.tasks.values():
            task.cancel()

        # Wait for tasks to complete
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        logger.info("Scheduler stopped")

    async def _schedule_plugin(self, plugin_name: str):
        """Schedule data collection for a plugin"""
        while self.is_running:
            try:
                # Collect data
                await self.collect_data(plugin_name)

                # Calculate next run time based on schedule
                next_run = self._get_next_run_time(plugin_name)
                delay = (next_run - datetime.now()).total_seconds()

                if delay > 0:
                    await asyncio.sleep(delay)
                else:
                    await asyncio.sleep(60)  # Wait 1 minute before retry

            except Exception as e:
                logger.error(f"Error scheduling {plugin_name}: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error

    async def collect_data(self, plugin_name: str):
        """Collect data from a plugin"""
        logger.info(f"Collecting data from {plugin_name}")

        try:
            plugin = self.loader.plugins.get(plugin_name)
            if not plugin:
                logger.error(f"Plugin {plugin_name} not found")
                return

            # Call collect_data method
            if hasattr(plugin, "collect_data"):
                data = await plugin.collect_data()

                # Store in InfluxDB or send to analysis service
                await self._store_data(plugin_name, data)

                # Publish event
                await self.redis.publish(
                    "data_collection",
                    {
                        "plugin": plugin_name,
                        "status": "success",
                        "timestamp": datetime.now().isoformat()
                    }
                )

                logger.info(f"Collected {len(data) if isinstance(data, list) else 1} records from {plugin_name}")

        except Exception as e:
            logger.error(f"Error collecting data from {plugin_name}: {e}")

            # Publish error event
            await self.redis.publish(
                "data_collection",
                {
                    "plugin": plugin_name,
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                }
            )

    async def _store_data(self, plugin_name: str, data: Any):
        """Store collected data"""
        # Implementation depends on storage backend
        # For InfluxDB, use influxdb_client
        # For PostgreSQL, use postgres helper
        pass

    def _get_next_run_time(self, plugin_name: str) -> datetime:
        """Calculate next run time based on cron schedule"""
        # Simplified implementation
        # In production, use croniter library
        schedule = self.schedules.get(plugin_name, "0 * * * *")

        # Parse cron and calculate next run
        # For now, return 1 hour from now
        return datetime.now() + timedelta(hours=1)
```

- [ ] **Step 4: Create data collector Dockerfile and requirements**

```dockerfile
# services/data-collector/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-cache-dir --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:8002/health || exit 1

CMD ["python", "main.py"]
```

```text
# services/data-collector/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
asyncpg==0.29.0
aioredis==2.0.1
influxdb-client==1.39.0
apscheduler==3.10.4
pyyaml==6.0.1
croniter==2.0.1
```

- [ ] **Step 5: Commit data collector service**

```bash
git add services/data-collector/
git commit -m "feat(microservices): create data collection service with scheduler for plugins"
```

---

## Phase 5: Analysis Service Separation (1-2 days)

### Task 5.1: Create Analysis Service

**Files:**
- Create: `services/analysis/main.py`
- Move: `core/correlation_*.py`, `core/anomaly_*.py`, `core/knowledge_*.py` → `services/analysis/core/`

- [ ] **Step 1: Create analysis service directory**

```bash
mkdir -p /root/minder/services/analysis/core
```

- [ ] **Step 2: Move analysis logic files**

```bash
cp /root/minder/core/correlation_engine.py /root/minder/services/analysis/core/
cp /root/minder/core/advanced_correlation.py /root/minder/services/analysis/core/
cp /root/minder/core/anomaly_detection.py /root/minder/services/analysis/core/
cp /root/minder/core/knowledge_graph.py /root/minder/services/analysis/core/
cp /root/minder/core/knowledge_populator.py /root/minder/services/analysis/core/
```

- [ ] **Step 3: Create analysis service main.py**

```python
# services/analysis/main.py
from fastapi import FastAPI, BackgroundTasks
import uvicorn
import os
from shared.models.common import HealthResponse, ServiceStatus
from shared.config.base import BaseConfig
from shared.utils.logging import setup_logger
from shared.database.postgres import PostgresHelper
from shared.database.redis import RedisHelper
from qdrant_client import QdrantClient
from core.correlation_engine import CorrelationEngine
from core.anomaly_detection import AnomalyDetector
from core.knowledge_graph import KnowledgeGraph

SERVICE_NAME = "minder-analysis"
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8003"))
config = BaseConfig()
logger = setup_logger(SERVICE_NAME)

app = FastAPI(
    title="Minder Analysis Service",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Analysis components
correlation_engine: CorrelationEngine = None
anomaly_detector: AnomalyDetector = None
knowledge_graph: KnowledgeGraph = None

# Connections
postgres: PostgresHelper = None
redis: RedisHelper = None
qdrant: QdrantClient = None

@app.on_event("startup")
async def startup():
    global correlation_engine, anomaly_detector, knowledge_graph, postgres, redis, qdrant

    logger.info(f"Starting {SERVICE_NAME}...")

    # Connect to databases
    postgres = PostgresHelper(
        dsn=config.postgres_url,
        schema="correlation_schema"
    )
    await postgres.connect()
    await postgres.init_schema()

    redis = RedisHelper(url=config.redis_url)
    await redis.connect()

    # Connect to Qdrant
    qdrant_host = os.getenv("QDRANT_HOST", "qdrant")
    qdrant_port = int(os.getenv("QDRANT_PORT", "6333"))
    qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)

    # Initialize analysis components
    correlation_engine = CorrelationEngine(postgres, qdrant)
    anomaly_detector = AnomalyDetector(postgres, qdrant)
    knowledge_graph = KnowledgeGraph(postgres, qdrant)

    # Subscribe to data collection events
    await _subscribe_to_events()

    logger.info(f"{SERVICE_NAME} started successfully")

@app.on_event("shutdown")
async def shutdown():
    global postgres, redis, qdrant

    logger.info(f"Shutting down {SERVICE_NAME}...")

    if postgres:
        await postgres.disconnect()

    if redis:
        await redis.disconnect()

    if qdrant:
        qdrant.close()

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(
        service=SERVICE_NAME,
        status=ServiceStatus.HEALTHY,
        uptime_seconds=0.0
    )

async def _subscribe_to_events():
    """Subscribe to data collection events"""
    pubsub = await redis.subscribe("data_collection")

    async for message in pubsub.listen():
        try:
            event_data = json.loads(message["data"])

            if event_data["status"] == "success":
                # Trigger analysis on new data
                await _analyze_new_data(event_data["plugin"])

        except Exception as e:
            logger.error(f"Error processing event: {e}")

async def _analyze_new_data(plugin_name: str):
    """Analyze newly collected data"""
    logger.info(f"Analyzing data from {plugin_name}")

    try:
        # Run correlations
        await correlation_engine.calculate_correlations(plugin_name)

        # Run anomaly detection
        await anomaly_detector.detect_anomalies(plugin_name)

        # Update knowledge graph
        await knowledge_graph.update(plugin_name)

    except Exception as e:
        logger.error(f"Error analyzing data from {plugin_name}: {e}")

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=SERVICE_PORT,
        reload=False
    )
```

- [ ] **Step 4: Create analysis service Dockerfile and requirements**

```dockerfile
# services/analysis/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-cache-dir --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:8003/health || exit 1

CMD ["python", "main.py"]
```

```text
# services/analysis/requirements.txt
fastapi==0.109.0
uvicorn[standard]==0.27.0
pydantic==2.5.3
asyncpg==0.29.0
aioredis==2.0.1
qdrant-client==1.7.0
numpy==1.26.3
pandas==2.1.4
scipy==1.11.4
scikit-learn==1.4.0
networkx==3.2.1
pyyaml==6.0.1
```

- [ ] **Step 5: Commit analysis service**

```bash
git add services/analysis/
git commit -m "feat(microservices): create analysis service with correlation, anomaly detection, and knowledge graph"
```

---

## Phase 6: API Gateway Completion (1 day)

### Task 6.1: Add Rate Limiting and Caching

**Files:**
- Modify: `services/gateway/middleware.py`
- Create: `services/gateway/cache.py`
- Create: `services/gateway/rate_limit.py`

- [ ] **Step 1: Create rate limiting middleware**

```python
# services/gateway/rate_limit.py
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
import time
import logging
from shared.database.redis import RedisHelper

logger = logging.getLogger(__name__)

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware using Redis"""

    def __init__(self, app, redis: RedisHelper, requests_per_minute: int = 60):
        super().__init__(app)
        self.redis = redis
        self.requests_per_minute = requests_per_minute

    async def dispatch(self, request: Request, call_next):
        # Get client identifier
        client_id = self._get_client_id(request)

        # Check rate limit
        key = f"rate_limit:{client_id}"
        current = await self.redis.get(key)

        if current is None:
            # First request
            await self.redis.set(key, 1, ttl=60)
        else:
            current = int(current)
            if current >= self.requests_per_minute:
                logger.warning(f"Rate limit exceeded for {client_id}")
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded"
                )
            await self.redis.set(key, current + 1, ttl=60)

        return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """Get client identifier from request"""
        # Use API key if available
        api_key = request.headers.get("X-API-Key")
        if api_key:
            return f"api_key:{api_key}"

        # Use IP address
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return f"ip:{forwarded_for.split(',')[0].strip()}"

        return f"ip:{request.client.host}"
```

- [ ] **Step 2: Create caching middleware**

```python
# services/gateway/cache.py
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import hashlib
import json
import logging
from shared.database.redis import RedisHelper

logger = logging.getLogger(__name__)

class CacheMiddleware(BaseHTTPMiddleware):
    """Response caching middleware"""

    def __init__(self, app, redis: RedisHelper, default_ttl: int = 300):
        super().__init__(app)
        self.redis = redis
        self.default_ttl = default_ttl

    async def dispatch(self, request: Request, call_next):
        # Only cache GET requests
        if request.method != "GET":
            return await call_next(request)

        # Skip cache for auth endpoints
        if "/auth/" in request.url.path:
            return await call_next(request)

        # Generate cache key
        cache_key = self._generate_cache_key(request)

        # Try to get from cache
        cached_response = await self.redis.get(cache_key)
        if cached_response:
            logger.debug(f"Cache hit: {cache_key}")
            return Response(
                content=json.dumps(cached_response["body"]),
                status_code=cached_response["status_code"],
                media_type=cached_response["media_type"],
                headers=cached_response["headers"]
            )

        # Cache miss - process request
        response = await call_next(request)

        # Cache response (only successful responses)
        if response.status_code == 200:
            body = response.body.decode()
            try:
                body_json = json.loads(body)
                await self.redis.set(
                    cache_key,
                    {
                        "body": body_json,
                        "status_code": response.status_code,
                        "media_type": response.media_type,
                        "headers": dict(response.headers)
                    },
                    ttl=self.default_ttl
                )
                logger.debug(f"Cached response: {cache_key}")
            except json.JSONDecodeError:
                pass  # Don't cache non-JSON responses

        return response

    def _generate_cache_key(self, request: Request) -> str:
        """Generate cache key from request"""
        # Include method, path, and query params
        key_parts = [
            request.method,
            request.url.path,
            str(sorted(request.query_params.items()))
        ]

        key_string = ":".join(key_parts)
        return f"cache:{hashlib.md5(key_string.encode()).hexdigest()}"
```

- [ ] **Step 3: Update gateway main.py to use new middleware**

```python
# services/gateway/main.py (additions)
from rate_limit import RateLimitMiddleware
from cache import CacheMiddleware

# In startup function
@app.on_event("startup")
async def startup():
    global redis

    # ... existing redis initialization ...

    # Add rate limiting and caching middleware
    app.add_middleware(RateLimitMiddleware, redis=redis, requests_per_minute=60)
    app.add_middleware(CacheMiddleware, redis=redis, default_ttl=300)
```

- [ ] **Step 4: Commit gateway enhancements**

```bash
git add services/gateway/
git commit -m "feat(microservices): add rate limiting and response caching to API gateway"
```

### Task 6.2: End-to-End Testing

**Files:**
- Create: `tests/integration/test_microservices.py`

- [ ] **Step 1: Create integration test suite**

```python
# tests/integration/test_microservices.py
import pytest
import httpx
import asyncio
from datetime import datetime

class TestMicroservicesIntegration:
    """Test microservices integration"""

    @pytest.fixture
    async def gateway_client(self):
        """Create HTTP client for gateway"""
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            yield client

    @pytest.mark.asyncio
    async def test_gateway_health(self, gateway_client):
        """Test gateway health endpoint"""
        response = await gateway_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "minder-gateway"
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_auth_service_routing(self, gateway_client):
        """Test routing to auth service"""
        # Test user registration
        response = await gateway_client.post(
            "/api/auth/register",
            json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "testpass123"
            }
        )
        assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_plugin_service_routing(self, gateway_client):
        """Test routing to plugin service"""
        response = await gateway_client.get("/api/plugins/")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data.get("plugins"), list)

    @pytest.mark.asyncio
    async def test_data_collection_trigger(self, gateway_client):
        """Test triggering data collection"""
        response = await gateway_client.post("/api/data/collect/tefas")
        assert response.status_code in [200, 202]

    @pytest.mark.asyncio
    async def test_rate_limiting(self, gateway_client):
        """Test rate limiting"""
        # Make many requests quickly
        responses = []
        for _ in range(65):  # Exceed limit of 60
            response = await gateway_client.get("/health")
            responses.append(response)

        # Check if any were rate limited
        rate_limited = any(r.status_code == 429 for r in responses)
        assert rate_limited, "Expected rate limit to be enforced"

    @pytest.mark.asyncio
    async def test_caching(self, gateway_client):
        """Test response caching"""
        # First request
        response1 = await gateway_client.get("/api/plugins/")
        assert response1.status_code == 200

        # Second request (should be cached)
        response2 = await gateway_client.get("/api/plugins/")
        assert response2.status_code == 200

        # Check cache header
        assert "x-cache" in response2.headers.lower()
```

- [ ] **Step 2: Run integration tests**

```bash
cd /root/minder
pytest tests/integration/test_microservices.py -v
```

- [ ] **Step 3: Commit integration tests**

```bash
git add tests/integration/
git commit -m "test(microservices): add integration tests for microservices architecture"
```

---

## Plugin Documentation

### Task 7.1: Create Plugin Development Guide

**Files:**
- Create: `docs/plugin-development/README.md`
- Create: `docs/plugin-development/quickstart.md`
- Create: `docs/plugin-development/advanced.md`
- Create: `plugins/plugin_template/`

- [ ] **Step 1: Create plugin development README**

```markdown
# Minder Plugin Development Guide

Welcome to the Minder plugin development guide! This guide will help you create, deploy, and manage plugins for the Minder platform.

## What is a Minder Plugin?

A Minder plugin is a self-contained module that collects, processes, or analyzes data. Plugins run in isolated environments and can optionally have their own Docker containers.

## Quick Start

Create your first plugin in 10 minutes: See [Quick Start Guide](quickstart.md)

## Plugin Structure

Basic plugin structure:
```
my_plugin/
├── plugin.yaml          # Plugin manifest
├── my_plugin_module.py  # Plugin implementation
└── requirements.txt     # Dependencies (optional)
```

Advanced plugin with custom container:
```
my_plugin/
├── plugin.yaml          # Plugin manifest
├── Dockerfile           # Custom container definition
├── docker-compose.yml   # Additional services (optional)
├── requirements.txt     # Python dependencies
├── my_plugin_module.py  # Plugin implementation
└── collectors/          # Additional modules
    └── data_collector.py
```

## Module Interface v2

Every plugin must implement two methods:

```python
from core.module_interface_v2 import BaseModule

class MyPlugin(BaseModule):
    def register(self):
        """Register plugin with Minder"""
        return {
            "name": "my_plugin",
            "version": "1.0.0",
            "description": "My awesome plugin"
        }

    async def health_check(self):
        """Check plugin health"""
        return {"status": "healthy"}
```

See [Advanced Guide](advanced.md) for more details.

## Custom Containers

Your plugin can have its own Docker container:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV PLUGIN_NAME=my_plugin
CMD ["python", "-m", "my_plugin_module"]
```

## Testing Your Plugin

```bash
# Test locally
python -m pytest tests/test_my_plugin.py

# Test in container
docker build -t my-plugin .
docker run -p 8005:8005 my-plugin
```

## Publishing Your Plugin

1. Add your plugin to the `plugins/` directory
2. Ensure `plugin.yaml` is complete
3. Test thoroughly
4. Submit pull request

## Need Help?

- Check existing plugins: `plugins/tefas/`, `plugins/news/`
- Read API docs: http://localhost:8000/docs
- Join our community
```

- [ ] **Step 2: Create quickstart guide**

```markdown
# Plugin Quick Start - Create Your First Plugin in 10 Minutes

## Step 1: Create Plugin Directory

```bash
cd /root/minder/plugins
mkdir my_first_plugin
cd my_first_plugin
```

## Step 2: Create Plugin Manifest

Create `plugin.yaml`:

```yaml
name: my_first_plugin
version: 1.0.0
description: My first Minder plugin
author: Your Name
```

## Step 3: Implement Plugin

Create `my_first_plugin_module.py`:

```python
from core.module_interface_v2 import BaseModule
from typing import Dict, Any

class MyFirstPlugin(BaseModule):
    def register(self) -> Dict[str, Any]:
        return {
            "name": "my_first_plugin",
            "version": "1.0.0",
            "description": "My first Minder plugin",
            "author": "Your Name"
        }

    async def health_check(self) -> Dict[str, Any]:
        return {
            "status": "healthy",
            "message": "Plugin is running!"
        }

    async def collect_data(self) -> list:
        """Collect some data"""
        return [
            {"id": 1, "value": "data1"},
            {"id": 2, "value": "data2"}
        ]
```

## Step 4: Test Your Plugin

```bash
# From minder root
python -c "
from core.plugin_loader import PluginLoader
import asyncio

async def test():
    loader = PluginLoader({'plugins_path': 'plugins'})
    await loader.load_plugin('my_first_plugin')
    plugin = loader.plugins['my_first_plugin']
    print(plugin.register())
    print(await plugin.health_check())

asyncio.run(test())
"
```

## Step 5: Deploy Your Plugin

```bash
# If using custom container
cd my_first_plugin
docker build -t my-first-plugin .
docker run -p 8005:8005 my-first-plugin
```

Or let Minder Plugin Service load it automatically!

## Congratulations!

You've created your first plugin! 🎉

## Next Steps

- Add data collection logic
- Create custom container
- Add unit tests
- Publish to community

See [Advanced Guide](advanced.md) for more.
```

- [ ] **Step 3: Create plugin template directory**

```bash
mkdir -p /root/minder/plugins/plugin_template
```

- [ ] **Step 4: Create template files**

```yaml
# plugins/plugin_template/plugin.yaml
name: "{{plugin_name}}"
version: 1.0.0
description: "Description of {{plugin_name}}"
author: "Your Name"
requires: []
container:
  image: "{{plugin_name}}-plugin:latest"
  port: 8005
```

```python
# plugins/plugin_template/{{plugin_name}}_module.py
from core.module_interface_v2 import BaseModule
from typing import Dict, Any, List

class {{PluginName}}Plugin(BaseModule):
    """Template for Minder plugins"""

    def register(self) -> Dict[str, Any]:
        return {
            "name": "{{plugin_name}}",
            "version": "1.0.0",
            "description": "Description of {{plugin_name}}",
            "author": "Your Name"
        }

    async def health_check(self) -> Dict[str, Any]:
        """Check plugin health"""
        return {
            "status": "healthy",
            "uptime_seconds": 0.0
        }

    async def collect_data(self) -> List[Dict[str, Any]]:
        """Collect data from external source"""
        # TODO: Implement data collection logic
        return []

    async def analyze(self, data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze collected data"""
        # TODO: Implement analysis logic
        return {"analysis": "results"}
```

```dockerfile
# plugins/plugin_template/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy plugin code
COPY . .

# Plugin configuration
ENV PLUGIN_NAME={{plugin_name}}
ENV PLUGIN_PORT=8005

# Health check
HEALTHCHECK --interval=30s --timeout=3s \
    CMD curl -f http://localhost:${PLUGIN_PORT}/health || exit 1

# Run plugin
CMD ["python", "-m", "{{plugin_name}}_module"]
```

```text
# plugins/plugin_template/requirements.txt
# Add your plugin's dependencies here
fastapi==0.109.0
httpx==0.26.0
pydantic==2.5.3
```

- [ ] **Step 5: Commit plugin documentation and template**

```bash
git add docs/plugin-development/ plugins/plugin_template/
git commit -m "docs(microservices): add comprehensive plugin development guide and template"
```

---

## Final Testing and Deployment

### Task 8.1: Deploy All Services

**Files:**
- Create: `scripts/deploy-microservices.sh`
- Create: `scripts/test-microservices.sh`

- [ ] **Step 1: Create deployment script**

```bash
#!/bin/bash
# scripts/deploy-microservices.sh

set -e

echo "🚀 Deploying Minder Microservices..."

# Stop existing services
echo "⏹️  Stopping existing services..."
docker-compose down

# Build all service images
echo "🔨 Building service images..."
docker-compose -f docker-compose.services.yml build

# Start infrastructure
echo "🏗️  Starting infrastructure services..."
docker-compose up -d postgres influxdb qdrant redis

# Wait for services to be healthy
echo "⏳ Waiting for infrastructure to be ready..."
sleep 10

# Start business services
echo "🚀 Starting business services..."
docker-compose -f docker-compose.services.yml up -d

# Wait for services to start
echo "⏳ Waiting for services to start..."
sleep 15

# Check service health
echo "🏥 Checking service health..."
for service in gateway auth plugins data analysis; do
    echo "Checking $service..."
    curl -f http://localhost:8000/health || echo "⚠️  $service not healthy"
done

echo "✅ Deployment complete!"
echo "📊 Dashboard: http://localhost:3002 (Grafana)"
echo "📖 API Docs: http://localhost:8000/docs"
```

- [ ] **Step 2: Create testing script**

```bash
#!/bin/bash
# scripts/test-microservices.sh

set -e

echo "🧪 Testing Minder Microservices..."

# Test gateway health
echo "Testing Gateway..."
curl -f http://localhost:8000/health | jq .

# Test auth service
echo "Testing Auth Service..."
curl -f http://localhost:8000/api/auth/health | jq .

# Test plugin service
echo "Testing Plugin Service..."
curl -f http://localhost:8000/api/plugins/health | jq .

# Test data service
echo "Testing Data Service..."
curl -f http://localhost:8000/api/data/health | jq .

# Test analysis service
echo "Testing Analysis Service..."
curl -f http://localhost:8000/api/correlations/health | jq .

echo "✅ All tests passed!"
```

- [ ] **Step 3: Make scripts executable**

```bash
chmod +x /root/minder/scripts/deploy-microservices.sh
chmod +x /root/minder/scripts/test-microservices.sh
```

- [ ] **Step 4: Deploy and test**

```bash
cd /root/minder
./scripts/deploy-microservices.sh
./scripts/test-microservices.sh
```

- [ ] **Step 5: Commit deployment scripts**

```bash
git add scripts/
git commit -m "devops(microservices): add deployment and testing scripts for microservices"
```

---

## Summary

This implementation plan transforms Minder from a monolithic FastAPI application to a domain-driven microservices architecture with:

✅ **5 Independent Services:** Gateway, Auth, Plugins, Data Collection, Analysis
✅ **Plugin Deployment System:** Plugins can deploy custom containers
✅ **Shared Library:** Common models, config, database helpers
✅ **Database Stratification:** PostgreSQL schemas, InfluxDB, Qdrant, Redis
✅ **Service Communication:** HTTP, Redis Pub/Sub, message queues
✅ **Complete Documentation:** Plugin development guides
✅ **Deployment Automation:** Scripts for easy deployment

**Total Estimated Time:** 7-10 days
**Total Tasks:** 25 tasks across 6 phases

Ready to execute! 🚀
