# Task 25: Test Dynamic AI Tools System - BLOCKED

**Date:** 2026-04-24
**Status:** ❌ **BLOCKED** - Critical implementation gaps prevent testing
**Reported By:** Task 25 Implementation

---

## Executive Summary

Testing of the dynamic AI tools system cannot proceed due to critical missing implementations in Tasks 21-24. While the manifests and aggregation endpoints are in place, the actual plugin execution layer is not functional.

---

## What Was Supposed to Work

### Expected Flow
1. Plugin declares AI tool in `manifest.yml` with `endpoint: /analysis`
2. Plugin Registry aggregates tools and returns `/v1/plugins/crypto/analysis`
3. API Gateway receives tool execution request
4. API Gateway proxies to `http://plugin-registry:8001/v1/plugins/crypto/analysis`
5. Plugin Registry proxies to actual plugin service
6. Plugin executes analysis and returns AI-formatted response

---

## What Actually Exists

### ✅ Completed Components

1. **Task 21 - Tool Schema Validation** (DONE)
   - `src/shared/ai/tool_schema.py` - Pydantic models created
   - `src/shared/ai/tool_validator.py` - Validation logic implemented
   - Unit tests passing

2. **Task 22 - Plugin Registry Aggregation** (DONE)
   - `/v1/plugins/ai/tools` endpoint exists
   - Aggregates tools from all plugin manifests
   - Returns OpenAI-compatible format
   - **Verified working**: Returns 5 tools correctly

3. **Task 23 - API Gateway Dynamic Discovery** (DONE)
   - Replaced hardcoded tools with dynamic discovery
   - 60-second caching implemented
   - Fetches from Plugin Registry
   - **Verified working**: Fetches tools correctly

4. **Task 24 - Plugin Manifests** (PARTIAL)
   - ✅ `ai_tools` sections added to all 5 manifests
   - ✅ Tool definitions properly formatted
   - ❌ **MISSING**: Actual `/analysis` endpoints in plugin.py files

### ❌ Critical Missing Components

1. **Plugin Service Endpoints** (MISSING)
   - Plugins don't have FastAPI routers
   - No `/analysis` endpoints exist in any plugin
   - Plugin.py files are old module-based classes, not FastAPI apps

2. **Plugin Registry Proxy** (MISSING)
   - Plugin Registry returns endpoints it doesn't handle
   - No proxy logic to forward requests to plugins
   - No mechanism to load plugin modules and call their functions

3. **Plugin Service Architecture** (UNCLEAR)
   - Plugins mounted as volumes, not running as services
   - No port assignments for plugins
   - No service discovery mechanism
   - Architecture decision needed: Run plugins as services OR implement in-process loading

---

## Test Results

### Step 1: Tool Execution Tests

```bash
for tool in get_crypto_price get_latest_news get_weather_data get_network_metrics get_tefas_funds; do
  curl -X POST http://localhost:8000/v1/ai/functions/$tool
done
```

**Result:** ❌ **ALL 5 TOOLS FAILED**

**Error:**
```json
{
  "detail": "Function execution failed: Client error '404 Not Found' for url 'http://minder-plugin-registry:8001/v1/plugins/crypto/analysis'"
}
```

**Root Cause:** The endpoint `/v1/plugins/crypto/analysis` doesn't exist in Plugin Registry

### Step 2: Tool Definitions Format

```bash
curl http://localhost:8000/v1/ai/functions/definitions | jq '.tools[0]'
```

**Result:** ✅ **WORKS**

Tool definitions are properly formatted with correct metadata:
- `type: "function"`
- `function.name`, `function.description`, `function.parameters`
- `metadata.plugin`, `metadata.endpoint`, `metadata.method`

### Step 3: Tool Caching

```bash
time curl http://localhost:8000/v1/ai/functions/definitions
```

**Result:** ✅ **WORKS**

First call: ~200ms
Second call: ~20ms (from cache)

### Step 4: Plugin Registry Tools Endpoint

```bash
curl http://localhost:8001/v1/plugins/ai/tools | jq '.tools | length'
```

**Result:** ✅ **WORKS**

Returns 5 tools correctly

---

## Architecture Gap Analysis

### Problem 1: Plugin Execution Layer Missing

**Current State:**
```yaml
# src/plugins/crypto/manifest.yml
ai_tools:
  - name: get_crypto_price
    endpoint: /analysis  # ❌ This endpoint doesn't exist
    method: GET
```

**What's Needed:**
```python
# src/plugins/crypto/plugin.py
from fastapi import APIRouter, Query
from src.shared.database import get_db

router = APIRouter()

@router.get("/analysis")
async def get_crypto_analysis(
    symbol: str = Query(..., description="Crypto symbol"),
    db: AsyncSession = Depends(get_db)
):
    """Get crypto price analysis for AI"""
    # Query database
    result = await db.execute(query)

    # Return AI-formatted response
    return {
        "price": result["price"],
        "market_cap": result["market_cap"],
        "change_24h": result["change_24h"],
        "timestamp": datetime.now().isoformat()
    }
```

### Problem 2: Plugin Registry Proxy Missing

**Current State:**
```python
# services/plugin-registry/main.py
@app.get("/v1/plugins/ai/tools")
async def get_all_ai_tools():
    """Returns tools with endpoints like /v1/plugins/crypto/analysis"""
    # But Plugin Registry doesn't handle these endpoints!
```

**What's Needed (Option A - Separate Services):**
```yaml
# infrastructure/docker/docker-compose.yml
services:
  crypto-plugin:
    build: ../../src/plugins/crypto
    ports:
      - "8002:8000"
    networks:
      - minder-network
```

**What's Needed (Option B - In-Process Loading):**
```python
# services/plugin-registry/main.py
@app.api_route("/v1/plugins/{plugin_name}/analysis", methods=["GET", "POST"])
async def proxy_plugin_request(plugin_name: str, request: Request):
    """Proxy request to plugin module loaded dynamically"""
    plugin = load_plugin_module(plugin_name)
    return await plugin.execute_analysis(request)
```

### Problem 3: Architecture Decision Needed

**Option A: Microservices (Recommended)**
- ✅ True isolation
- ✅ Independent scaling
- ✅ Technology flexibility
- ❌ More complex deployment
- ❌ More resources

**Option B: In-Process Plugin Loading**
- ✅ Simpler deployment
- ✅ Lower resource usage
- ✅ Faster development
- ❌ Shared execution context
- ❌ Plugin can crash registry
- ❌ Language locked to Python

---

## Required Fixes Before Testing Can Proceed

### Fix Option A: Run Plugins as Services (Recommended)

1. **Create FastAPI app for each plugin**
   ```bash
   src/plugins/crypto/app.py  # New FastAPI application
   src/plugins/news/app.py
   src/plugins/weather/app.py
   src/plugins/network/app.py
   src/plugins/tefas/app.py
   ```

2. **Add plugin services to docker-compose.yml**
   ```yaml
   crypto-plugin:
     build: ./src/plugins/crypto
     container_name: minder-crypto-plugin
     ports:
       - "8002:8000"
     environment:
       - DATABASE_URL=postgresql://...
     depends_on:
       - postgres
     networks:
       - minder-network
   ```

3. **Update Plugin Registry to proxy to plugin services**
   ```python
   @app.api_route("/v1/plugins/{plugin_name}/{path:path}")
   async def proxy_to_plugin(plugin_name: str, path: str, request: Request):
       url = f"http://minder-{plugin_name}-plugin:8000/{path}"
       return await proxy_request(url, request)
   ```

### Fix Option B: In-Process Plugin Loading (Faster)

1. **Add FastAPI router to each plugin.py**
   ```python
   # src/plugins/crypto/plugin.py
   from fastapi import APIRouter

   router = APIRouter()

   @router.get("/analysis")
   async def analysis(symbol: str):
       # Implementation
   ```

2. **Load plugin routers in Plugin Registry**
   ```python
   # services/plugin-registry/main.py
   from src.plugins.crypto.plugin import router as crypto_router
   from src.plugins.news.plugin import router as news_router

   app.include_router(crypto_router, prefix="/v1/plugins/crypto")
   app.include_router(news_router, prefix="/v1/plugins/news")
   ```

---

## Impact Assessment

### Tasks Affected
- ❌ **Task 25**: Cannot test (current task)
- ❌ **Task 24**: Incomplete - endpoints missing
- ⚠️ **Task 23**: Works but can't verify end-to-end
- ⚠️ **Task 22**: Works but can't verify end-to-end
- ✅ **Task 21**: Complete and tested

### Project Impact
- **OpenWebUI Integration**: Cannot use AI tools
- **Plugin System**: Non-functional for AI workflows
- **Documentation**: Cannot complete user guides
- **Production**: Feature is broken

---

## Recommendations

### Immediate Actions (Critical Path)

1. **Choose Architecture**
   - Decide between Option A (microservices) or Option B (in-process)
   - **Recommendation**: Start with Option B for faster testing, migrate to Option A for production

2. **Implement Plugin Endpoints**
   - Add `/analysis` endpoint to each of 5 plugins
   - Implement database queries
   - Return AI-formatted responses

3. **Add Plugin Registry Proxy**
   - Implement proxy logic for `/v1/plugins/{plugin_name}/analysis`
   - Handle errors gracefully
   - Add logging and metrics

4. **Update Docker Configuration**
   - Either add plugin services to docker-compose.yml (Option A)
   - Or ensure plugins are importable by Plugin Registry (Option B)

5. **Re-run Task 25 Tests**
   - Verify all 5 tools execute successfully
   - Check response formats
   - Validate caching behavior

### Long-term Actions

1. **Add Plugin Development Documentation**
   - How to create AI tools
   - Endpoint patterns
   - Response format standards

2. **Add Plugin Testing**
   - Unit tests for each tool
   - Integration tests for proxy
   - End-to-end tests

3. **Add Monitoring**
   - Track tool execution metrics
   - Monitor plugin health
   - Alert on failures

---

## Conclusion

**Status:** ❌ **BLOCKED**

The dynamic AI tools system has a solid foundation (Tasks 21-23 complete) but cannot function without the plugin execution layer (Task 24 incomplete). The system is **80% complete** but the missing **20% is critical**.

**Estimated Effort to Unblock:**
- Option B (in-process): 4-6 hours
- Option A (microservices): 8-12 hours

**Recommended Path:**
1. Implement Option B today to unblock testing
2. Verify all tests pass
3. Plan migration to Option A for production scalability

**Next Step:**
Await decision on architecture approach before proceeding with implementation.

---

**Blocked By:** Task 24 incomplete - plugin endpoints missing
**Blocking:** Task 25 testing, OpenWebUI integration, production deployment
