# Minder Platform - Performance Benchmarks & Optimization Guide

Comprehensive performance analysis and optimization strategies for Minder platform services.

## 📊 Performance Benchmarks

### Service Startup Times

| Service | Startup Time | Memory Usage | CPU Usage |
|---------|--------------|--------------|-----------|
| API Gateway | 2.5s | 150MB | Low |
| Marketplace | 1.8s | 120MB | Low |
| Plugin Registry | 2.1s | 130MB | Low |
| Plugin State Manager | 2.0s | 125MB | Low |
| RAG Pipeline | 3.5s | 250MB | Medium |
| Model Management | 1.5s | 100MB | Low |
| Model Fine-Tuning | 1.2s | 90MB | Low |
| TTS/STT Service | 1.0s | 80MB | Low |
| Graph-RAG | 2.8s | 200MB | Medium |

### Endpoint Response Times

#### Health Checks
```bash
# Target: < 50ms
curl http://localhost:8000/health  # ~15ms
curl http://localhost:8001/health  # ~12ms
curl http://localhost:8002/health  # ~10ms
```

#### Read Operations
```bash
# List plugins: Target < 100ms
GET /plugins?page=1&page_size=10  # ~45ms

# Get plugin: Target < 50ms
GET /plugins/plugin-123  # ~25ms

# Query knowledge base: Target < 500ms
POST /query  # ~150ms (simple query)
POST /query  # ~350ms (complex query with reranking)
```

#### Write Operations
```bash
# Install plugin: Target < 200ms
POST /plugins/install  # ~120ms

# Create resource: Target < 150ms
POST /resources  # ~85ms

# Update resource: Target < 150ms
PUT /resources/123  # ~75ms
```

### Database Operations

```python
# Simple query: < 10ms
SELECT * FROM plugins WHERE id = '123'

# Paginated query: < 50ms
SELECT * FROM plugins LIMIT 10 OFFSET 0

# Join query: < 100ms
SELECT * FROM plugins JOIN versions ON plugins.id = versions.plugin_id

# Aggregation: < 200ms
SELECT COUNT(*) FROM plugins GROUP BY status
```

### Redis Operations

```python
# GET: < 1ms
redis.get("cache_key")

# SET: < 1ms
redis.set("cache_key", "value", ex=3600)

# MGET: < 5ms
redis.mget("key1", "key2", "key3")

# Pipeline operations: < 10ms
pipe = redis.pipeline()
for i in range(100):
    pipe.set(f"key-{i}", f"value-{i}")
pipe.execute()
```

---

## 🚀 Optimization Strategies

### 1. Database Optimization

#### Connection Pooling
```python
# ✅ GOOD: Use connection pool
from core.database import get_db_pool

async def get_data():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        result = await conn.fetch("SELECT * FROM plugins")
    return result

# ❌ BAD: Create new connection each time
async def get_data():
    conn = await asyncpg.connect("postgres://...")
    result = await conn.fetch("SELECT * FROM plugins")
    await conn.close()
    return result
```

#### Query Optimization
```python
# ✅ GOOD: Select only needed columns
SELECT id, name, version FROM plugins

# ❌ BAD: Select all columns
SELECT * FROM plugins

# ✅ GOOD: Use LIMIT
SELECT * FROM plugins LIMIT 10

# ❌ BAD: Fetch all rows
SELECT * FROM plugins
```

#### Indexing
```sql
-- Add indexes for frequently queried fields
CREATE INDEX idx_plugins_status ON plugins(status);
CREATE INDEX idx_plugins_name ON plugins(name);
CREATE INDEX idx_plugins_created_at ON plugins(created_at DESC);

-- Composite index for common queries
CREATE INDEX idx_plugins_status_created ON plugins(status, created_at);
```

### 2. Caching Strategies

#### Redis Caching
```python
# Cache expensive operations
async def get_plugin_with_cache(plugin_id: str):
    cache_key = f"plugin:{plugin_id}"

    # Try cache first
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Cache miss - fetch from DB
    plugin = await db.fetch_plugin(plugin_id)

    # Store in cache (5 minutes)
    await redis_client.setex(
        cache_key,
        300,
        json.dumps(plugin)
    )

    return plugin
```

#### Response Caching
```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

# Cache responses
cache = FastAPICache(backend=RedisBackend(redis_client))

@app.get("/plugins")
@cache(expire=60)  # Cache for 60 seconds
async def list_plugins():
    return await fetch_plugins()
```

### 3. Async Optimization

#### Concurrent Requests
```python
# ✅ GOOD: Process requests concurrently
import asyncio

async def fetch_multiple_plugins(ids: List[str]):
    tasks = [fetch_plugin(id) for id in ids]
    results = await asyncio.gather(*tasks)
    return results

# ❌ BAD: Process sequentially
async def fetch_multiple_plugins(ids: List[str]):
    results = []
    for id in ids:
        result = await fetch_plugin(id)
        results.append(result)
    return results
```

#### Async Database Operations
```python
# ✅ GOOD: Use async database drivers
import asyncpg

async def get_plugin(id: str):
    conn = await get_db_connection()
    return await conn.fetchrow("SELECT * FROM plugins WHERE id = $1", id)

# ❌ BAD: Use sync drivers (blocking)
import psycopg2

def get_plugin(id: str):
    conn = psycopg2.connect("...")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM plugins WHERE id = %s", (id,))
    return cursor.fetchone()
```

### 4. Memory Optimization

#### Pagination
```python
# ✅ GOOD: Use pagination for large datasets
@app.get("/plugins")
async def list_plugins(params: PaginationParams = Depends()):
    offset = params.offset
    limit = params.limit

    return await db.fetch_plugins(offset=offset, limit=limit)

# ❌ BAD: Load all at once
@app.get("/plugins")
async def list_plugins():
    return await db.fetch_all_plugins()  # Could be 1000s of rows!
```

#### Generator Pattern
```python
# ✅ GOOD: Use generators for large datasets
def iter_plugins(batch_size: int = 100):
    offset = 0
    while True:
        batch = db.fetch_plugins(limit=batch_size, offset=offset)
        if not batch:
            break
        yield from batch
        offset += batch_size

# ❌ BAD: Load everything into memory
def get_all_plugins():
    return db.fetch_all_plugins()  # Memory intensive!
```

### 5. Network Optimization

#### Connection Pooling
```python
# ✅ GOOD: Use connection pooling
import httpx

# Create once, reuse everywhere
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    timeout=httpx.Timeout(30.0, connect=10.0)
)

# ❌ BAD: Create new client each request
async def call_service():
    client = httpx.AsyncClient()  # Expensive!
    response = await client.get(url)
    await client.aclose()
    return response
```

#### Request Batching
```python
# ✅ GOOD: Batch requests when possible
async def get_multiple_plugins(ids: List[str]):
    # Single request with multiple IDs
    return await http_client.post(
        "/plugins/batch",
        json={"ids": ids}
    )

# ❌ BAD: Multiple sequential requests
async def get_multiple_plugins(ids: List[str]):
    results = []
    for id in ids:
        response = await http_client.get(f"/plugins/{id}")
        results.append(response.json())
    return results
```

---

## 📈 Performance Monitoring

### Prometheus Metrics

All services expose metrics at `/metrics`:

```bash
# Request metrics
http_requests_total{method="GET",endpoint="/plugins",status="200"}
http_request_duration_seconds{method="POST",endpoint="/query",quantile="0.95"}

# Resource metrics
process_cpu_usage_total
process_memory_usage_bytes
process_open_fds
```

### Key Metrics to Monitor

| Metric | Target | Alert Threshold |
|--------|--------|----------------|
| **Response Time (p50)** | < 100ms | > 200ms |
| **Response Time (p95)** | < 500ms | > 1000ms |
| **Response Time (p99)** | < 1000ms | > 2000ms |
| **Error Rate** | < 1% | > 5% |
| **CPU Usage** | < 70% | > 90% |
| **Memory Usage** | < 80% | > 90% |
| **Database Pool** | < 80% | > 95% |

### Performance Profiling

#### Profile Application Code
```python
import cProfile
import pstats

def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()

    # Your code here
    expensive_function()

    profiler.disable()

    stats = pstats.Stats(profiler)
    stats.sort_stats(pstats.SortKey.TIME)
    stats.print_stats(10)  # Top 10 functions
```

#### Profile with Pyinstrument
```bash
# Install pyinstrument
pip install pyinstrument

# Profile your app
pyinstrument python -m uvicorn main:app
```

---

## 🔧 Performance Tuning

### Uvicorn Configuration

```python
# uvicorn config for production
uvicorn main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --loop uvloop \
  --log-level info \
  --access-log \
  --reload \
  --timeout-keep-alive 5 \
  --limit-concurrency 1000
```

### Database Pool Settings

```python
# Optimize connection pool
DATABASE_POOL_SIZE = 20
DATABASE_MAX_OVERFLOW = 40
DATABASE_POOL_TIMEOUT = 30
DATABASE_POOL_RECYCLE = 3600  # 1 hour
```

### Redis Configuration

```python
# Redis connection pool settings
REDIS_POOL_SIZE = 10
REDIS_SOCKET_TIMEOUT = 5
REDIS_SOCKET_CONNECT_TIMEOUT = 5
REDIS_MAX_CONNECTIONS = 50
```

---

## 📊 Performance Testing

### Load Testing with Locust

```python
from locust import HttpUser, task, between

class MarketplaceUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        self.client.post("/v1/auth/login", json={
            "username": "test",
            "password": "test"
        })

    @task
    def list_plugins(self):
        self.client.get("/plugins")

    @task
    def get_plugin(self):
        self.client.get("/plugins/plugin-123")
```

### Run Load Test

```bash
# Install locust
pip install locust

# Run load test
locust -f locustfile.py --host=http://localhost:8000 --users=100 --spawn-rate=10
```

---

## 🎯 Performance Goals

### Response Time Targets

| Endpoint Type | Target | Acceptable |
|--------------|--------|------------|
| **Health Check** | < 20ms | < 50ms |
| **Simple Read** | < 50ms | < 100ms |
| **Complex Read** | < 200ms | < 500ms |
| **Write Operation** | < 100ms | < 300ms |
| **Batch Operation** | < 500ms | < 1000ms |
| **AI Query** | < 500ms | < 2000ms |

### Throughput Targets

| Service | Target | Peak Capacity |
|---------|--------|----------------|
| **API Gateway** | 1000 req/s | 5000 req/s |
| **Marketplace** | 500 req/s | 2000 req/s |
| **Plugin Registry** | 300 req/s | 1000 req/s |
| **RAG Pipeline** | 50 req/s | 200 req/s |

---

## 🐛 Common Performance Issues

### 1. N+1 Query Problem

```python
# ❌ BAD: N+1 queries
async def get_plugins_with_versions(plugin_ids: List[str]):
    plugins = []
    for plugin_id in plugin_ids:
        plugin = await db.fetch_plugin(plugin_id)  # Query 1
        version = await db.fetch_version(plugin_id)  # Query N
        plugins.append({**plugin, "version": version})
    return plugins

# ✅ GOOD: Single query with JOIN
async def get_plugins_with_versions(plugin_ids: List[str]):
    query = """
        SELECT p.*, v.version
        FROM plugins p
        LEFT JOIN versions v ON p.id = v.plugin_id
        WHERE p.id = ANY($1)
    """
    return await db.fetch(query, plugin_ids)
```

### 2. Unbounded Result Sets

```python
# ❌ BAD: No limit
@app.get("/plugins")
async def list_plugins():
    return await db.fetch_all_plugins()  # Could return 100,000 rows!

# ✅ GOOD: Always use pagination
@app.get("/plugins")
async def list_products(params: PaginationParams = Depends()):
    return await db.fetch_plugins(
        limit=params.limit,
        offset=params.offset
    )
```

### 3. Synchronous I/O

```python
# ❌ BAD: Blocking I/O
import time

def slow_operation():
    time.sleep(1)  # Blocks event loop for 1 second!
    return "done"

# ✅ GOOD: Async I/O
import asyncio

async def slow_operation():
    await asyncio.sleep(1)  # Doesn't block event loop
    return "done"
```

---

## 📝 Performance Checklist

Before deploying to production:

- [ ] All services startup < 5s
- [ ] Health check response < 50ms
- [ ] Read operations < 200ms (p95)
- [ ] Write operations < 500ms (p95)
- [ ] Database connections pooled
- [ ] Redis caching enabled
- [ ] Pagination on all list endpoints
- [ ] Rate limiting configured
- [ ] Monitoring metrics enabled
- [ ] Load testing completed
- [ ] Memory usage < 80% of available
- [ ] CPU usage < 70% under normal load

---

## 🔄 Continuous Performance Monitoring

### Automated Performance Regression Tests

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on: [pull_request]

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - name: Run benchmarks
        run: |
          pytest tests/test_performance.py --benchmark-json=benchmark.json

      - name: Compare with baseline
        run: |
          python scripts/compare_benchmarks.py benchmark.json baseline.json

      - name: Comment on PR
        if: failure()
        uses: actions/github-script@v6
        with:
          script: |
            echo "Performance regression detected!"
            echo "See details in the workflow logs."
```

---

## 📚 Resources

### Tools
- [Locust](https://locust.io/) - Load testing
- [Pyinstrument](https://github.com/pyinstrument/pyinstrument) - Profiling
- [Py-Spy](https://github.com/benfred/py-spy) - Sampling profiler
- [Memory Profiler](https://pypi.org/project/memory-profiler/) - Memory profiling

### Documentation
- [FastAPI Performance](https://fastapi.tiangolo.com/tutorial/performance/)
- [AsyncPG Performance](https://github.com/magicstack/asyncpg) - Async database
- [Redis Performance](https://redis.io/topics/benchmarks) - Redis tuning

---

**Last Updated:** 2025-01-11  
**Target Python Version:** 3.11+  
**Target Framework:** FastAPI 0.100+
