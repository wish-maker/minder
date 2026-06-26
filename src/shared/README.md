# Minder Shared Components

Reusable utilities, models, and configurations for Minder platform services.

## 📦 Overview

This package provides common components used across all Minder services to:
- **Reduce code duplication** - Share utilities instead of rewriting
- **Ensure consistency** - Standard patterns for responses, requests, configurations
- **Improve maintainability** - Update once, apply everywhere
- **Accelerate development** - New services can use pre-built components

## 🚀 Quick Start

### 1. Import Shared Components

```python
# Utilities
from services.shared.utils import (
    create_redis_client_from_settings,
    add_cors_middleware,
    get_service_url,
)

# Models
from services.shared.models import (
    HealthCheckResponse,
    SuccessResponse,
    ErrorResponse,
    PaginationParams,
)

# Configuration
from services.shared.config import (
    MinderBaseSettings,
    get_service_settings,
)
```

### 2. Use in Your Service

```python
from services.shared.utils import create_redis_client_from_settings
from services.shared.models import HealthCheckResponse
from services.shared.config import MinderBaseSettings

class Settings(MinderBaseSettings):
    SERVICE_PORT: int = 8002

settings = Settings()

# Redis client
redis_client = create_redis_client_from_settings(settings)

# Health endpoint
@app.get("/health", response_model=HealthCheckResponse)
async def health_check():
    return HealthCheckResponse(
        service="my-service",
        status="healthy",
        version="1.0.0"
    )
```

## 📁 Package Structure

```
services/shared/
├── __init__.py
├── README.md
├── config/
│   ├── __init__.py
│   └── base_settings.py      # Base configuration class
├── models/
│   ├── __init__.py
│   ├── requests.py            # Common request models
│   └── responses.py           # Common response models
└── utils/
    ├── __init__.py
    ├── cors.py                # CORS middleware utilities
    ├── redis_client.py        # Redis client factory
    └── service_urls.py        # Service URL management
```

## 🔧 Components

### Configuration (`config/`)

#### `MinderBaseSettings`

Base settings class with common defaults:

```python
from services.shared.config import MinderBaseSettings

class Settings(MinderBaseSettings):
    # Already included:
    # - APP_NAME, VERSION, ENVIRONMENT
    # - DB_HOST, DB_PORT, DB_USER, DB_PASSWORD
    # - REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
    # - CORS_ALLOWED_ORIGINS
    # - LOG_LEVEL, JWT_SECRET, etc.

    # Add your service-specific settings
    CUSTOM_SETTING: str = "default_value"
```

#### `get_service_settings()`

Factory function for service-specific settings:

```python
from services.shared.config import get_service_settings

settings = get_service_settings(
    "marketplace",
    PORT=8002,
    DB_NAME="minder_marketplace"
)
```

### Models (`models/`)

#### Response Models

**Health Check**
```python
from services.shared.models import HealthCheckResponse

return HealthCheckResponse(
    service="marketplace",
    status="healthy",
    version="1.0.0",
    environment="production",
    checks={"database": "connected"}
)
```

**Success Response**
```python
from services.shared.models import SuccessResponse

return SuccessResponse[data=dict](
    message="Operation completed",
    data={"id": 123, "name": "Plugin"}
)
```

**Error Response**
```python
from services.shared.models import ErrorResponse

raise HTTPException(
    status_code=400,
    detail=ErrorResponse(
        error="Validation failed",
        detail={"field": "Invalid value"}
    ).model_dump()
)
```

**Paginated Response**
```python
from services.shared.models import PaginatedResponse

return PaginatedResponse.create(
    items=items,
    total=100,
    page=1,
    page_size=10
)
```

#### Request Models

**Pagination**
```python
from services.shared.models import PaginationParams

@app.get("/items")
async def list_items(params: PaginationParams = Depends()):
    offset = params.offset
    limit = params.limit
    # Query database...
```

**Search**
```python
from services.shared.models import SearchParams

@app.post("/search")
async def search(params: SearchParams):
    query = params.query
    filters = params.filters
    # Search...
```

### Utilities (`utils/`)

#### Redis Client

**Factory Functions**
```python
from services.shared.utils import create_redis_client_from_settings

# Auto-configure from settings object
redis_client = create_redis_client_from_settings(settings)

# Or manual configuration
from services.shared.utils import create_redis_client

redis_client = create_redis_client(
    host="localhost",
    port=6379,
    password="secret"
)
```

**Features**
- ✅ Automatic connection testing
- ✅ Proper error handling
- ✅ Consistent configuration

#### CORS Middleware

**Add CORS**
```python
from services.shared.utils import add_cors_middleware

add_cors_middleware(
    app,
    allowed_origins=["http://localhost:3000"],
    allow_credentials=True
)
```

**From String**
```python
from services.shared.utils import add_cors_from_string

add_cors_from_string(
    app,
    "http://localhost:3000,http://localhost:8000"
)
```

#### Service URLs

**Get Service URL**
```python
from services.shared.utils import get_service_url, get_endpoint

marketplace_url = get_service_url("MARKETPLACE")
# Returns: "http://minder-marketplace:8002"

health_endpoint = get_endpoint("MARKETPLACE", "/health")
# Returns: "http://minder-marketplace:8002/health"
```

**ServiceURLs Class**
```python
from services.shared.utils import ServiceURLs

# Access any service URL
url = ServiceURLs.MARKETPLACE
url = ServiceURLs.REDIS
url = ServiceURLs.OLLAMA

# Update from environment
ServiceURLs.update_from_env()
```

## 📖 Usage Examples

### Example 1: Creating a New Service

```python
# services/my-service/main.py
from fastapi import FastAPI
from services.shared.config import MinderBaseSettings
from services.shared.models import HealthCheckResponse
from services.shared.utils import (
    create_redis_client_from_settings,
    add_cors_middleware,
)

class Settings(MinderBaseSettings):
    PORT: int = 8010

settings = Settings()
app = FastAPI(title="My Service")

# Add CORS
add_cors_middleware(app)

# Initialize Redis
redis_client = create_redis_client_from_settings(settings)

@app.get("/health", response_model=HealthCheckResponse)
async def health():
    return HealthCheckResponse(
        service="my-service",
        status="healthy",
        version="1.0.0"
    )
```

### Example 2: Standardized Response

```python
from services.shared.models import (
    SuccessResponse,
    ErrorResponse,
    PaginatedResponse,
)

@app.post("/items", response_model=SuccessResponse[Item])
async def create_item(item: Item):
    created = await create_item_in_db(item)
    return SuccessResponse[data](
        message="Item created",
        data=created
    )

@app.get("/items", response_model=PaginatedResponse[Item])
async def list_items(params: PaginationParams = Depends()):
    items, total = await get_items_from_db(params)
    return PaginatedResponse.create(
        items=items,
        total=total,
        page=params.page,
        page_size=params.page_size
    )
```

### Example 3: Service Communication

```python
from services.shared.utils import get_endpoint
import httpx

async def call_marketplace():
    url = get_endpoint("MARKETPLACE", "/plugins")
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.json()
```

## 🔄 Migration Guide

### Before (Old Pattern)

```python
import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Duplicate Redis initialization
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    db=0,
)

# Duplicate CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom health check response
@app.get("/health")
async def health():
    return {
        "service": "my-service",
        "status": "healthy",
        "version": "1.0.0"
    }
```

### After (Using Shared Components)

```python
from services.shared.utils import (
    create_redis_client_from_settings,
    add_cors_middleware,
)
from services.shared.models import HealthCheckResponse

# Shared Redis initialization
redis_client = create_redis_client_from_settings(settings)

# Shared CORS setup
add_cors_middleware(app, allowed_origins=["http://localhost:3000"])

# Standardized health check
@app.get("/health", response_model=HealthCheckResponse)
async def health() -> HealthCheckResponse:
    return HealthCheckResponse(
        service="my-service",
        status="healthy",
        version="1.0.0"
    )
```

## 🎯 Best Practices

### 1. Always Use Shared Models

✅ **DO:**
```python
from services.shared.models import HealthCheckResponse

@app.get("/health", response_model=HealthCheckResponse)
async def health():
    return HealthCheckResponse(...)
```

❌ **DON'T:**
```python
@app.get("/health")
async def health():
    return {"service": "...", "status": "..."}
```

### 2. Use Factory Functions

✅ **DO:**
```python
redis_client = create_redis_client_from_settings(settings)
```

❌ **DON'T:**
```python
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    # ...
)
```

### 3. Extend Base Settings

✅ **DO:**
```python
class Settings(MinderBaseSettings):
    CUSTOM_FIELD: str = "default"
```

❌ **DON'T:**
```python
class Settings(BaseSettings):
    APP_NAME: str = "Service"  # Already in base
    REDIS_HOST: str = "redis"  # Already in base
    # ...
```

### 4. Use Type Hints

✅ **DO:**
```python
async def create_item(item: Item) -> SuccessResponse[Item]:
    ...
```

❌ **DON'T:**
```python
async def create_item(item):
    ...
```

## 📚 Related Documentation

- [API Documentation](../../docs/api/)
- [Architecture Overview](../../docs/architecture/)

## 🤝 Contributing

When adding new shared components:

1. **Place in appropriate directory** (`utils/`, `models/`, `config/`)
2. **Add docstrings** with examples
3. **Include type hints**
4. **Update this README**
5. **Add tests** (when test framework is ready)

## 📝 Version History

- **v1.0.0** (2025-01-11)
  - Initial release
  - Redis client factory
  - CORS utilities
  - Base settings class
  - Common request/response models
  - Service URL management
