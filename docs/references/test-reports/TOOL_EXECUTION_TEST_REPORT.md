# Tool Execution Test Report
**Date**: 2026-04-24
**Task**: Task 7 - Test Direct Tool Execution
**Status**: DONE_WITH_CONCERNS

## Executive Summary

Tested all 8 AI tool execution endpoints provided by the API Gateway. Only **3 out of 8 tools (37.5%)** are currently functional. The root cause is a mismatch between the API Gateway's function mappings and the actual Plugin Registry API endpoints.

## Test Results

### ✅ Working Tools (3/8)

| Tool | Endpoint | Status | Evidence |
|------|----------|--------|----------|
| `collect_crypto_data` | `/v1/ai/functions/collect_crypto_data` | ✅ PASS | Returns `{"status": "success", "result": {"status": "collecting"}}` |
| `collect_news` | `/v1/ai/functions/collect_news` | ✅ PASS | Returns `{"status": "success", "result": {"status": "collecting"}}` |
| `get_plugin_status` | `/v1/ai/functions/get_plugin_status` | ✅ PASS | Returns plugin list with 5 plugins, all healthy |

### ❌ Failed Tools (5/8)

| Tool | Endpoint | Error | Root Cause |
|------|----------|-------|------------|
| `get_crypto_price` | `/v1/ai/functions/get_crypto_price` | 404 Not Found | Calls non-existent `/v1/plugins/crypto/analysis` |
| `get_latest_news` | `/v1/ai/functions/get_latest_news` | 404 Not Found | Calls non-existent `/v1/plugins/news/analysis` |
| `get_network_metrics` | `/v1/ai/functions/get_network_metrics` | 404 Not Found | Calls non-existent `/v1/plugins/network/analysis` |
| `get_weather_data` | `/v1/ai/functions/get_weather_data` | 404 Not Found | Calls non-existent `/v1/plugins/weather/analysis` |
| `get_tefas_funds` | `/v1/ai/functions/get_tefas_funds` | 404 Not Found | Calls non-existent `/v1/plugins/tefas/analysis` |

## Root Cause Analysis

### Issue: Function Mapping Mismatch

**File**: `/root/minder/services/api-gateway/routes/ai.py`

The `FUNCTION_MAPPINGS` dictionary references endpoints that don't exist in the Plugin Registry:

```python
FUNCTION_MAPPINGS = {
    "get_crypto_price": {"url": "http://minder-plugin-registry:8001/v1/plugins/crypto/analysis", ...},  # ❌ 404
    "get_latest_news": {"url": "http://minder-plugin-registry:8001/v1/plugins/news/analysis", ...},     # ❌ 404
    "get_network_metrics": {"url": "http://minder-plugin-registry:8001/v1/plugins/network/analysis", ...}, # ❌ 404
    "get_weather_data": {"url": "http://minder-plugin-registry:8001/v1/plugins/weather/analysis", ...},   # ❌ 404
    "get_tefas_funds": {"url": "http://minder-plugin-registry:8001/v1/plugins/tefas/analysis", ...},    # ❌ 404
}
```

### Actual Plugin Registry Endpoints

According to the Plugin Registry OpenAPI spec, these endpoints exist:

```
/v1/plugins/{plugin_name}              # GET plugin info
/v1/plugins/{plugin_name}/collect      # POST trigger data collection
/v1/plugins/{plugin_name}/health       # GET plugin health status
```

**Missing**: `/v1/plugins/{plugin_name}/analysis` endpoint

## Detailed Test Commands

### Test 1: get_crypto_price
```bash
curl -X POST http://localhost:8000/v1/ai/functions/get_crypto_price \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC"}'
```
**Result**: ❌ 404 Not Found
**Error**: `Client error '404 Not Found' for url 'http://minder-plugin-registry:8001/v1/plugins/crypto/analysis?symbol=BTC'`

### Test 2: get_plugin_status
```bash
curl -X POST http://localhost:8000/v1/ai/functions/get_plugin_status \
  -H "Content-Type: application/json" \
  -d '{}'
```
**Result**: ✅ Success
**Response**: Returns 5 plugins (crypto, network, news, tefas, weather) - all healthy

### Test 3: collect_crypto_data
```bash
curl -X POST http://localhost:8000/v1/ai/functions/collect_crypto_data \
  -H "Content-Type: application/json" \
  -d '{}'
```
**Result**: ✅ Success
**Response**: `{"status": "success", "result": {"status": "collecting"}}`

### Batch Test Results
```bash
for tool in get_crypto_price collect_crypto_data get_latest_news collect_news get_plugin_status get_network_metrics get_weather_data get_tefas_funds; do
  echo "Testing $tool..."
  curl -s -X POST http://localhost:8000/v1/ai/functions/$tool \
    -H "Content-Type: application/json" \
    -d '{}' | jq -r '.status' | grep -q success && echo "✅ $tool works" || echo "❌ $tool failed"
done
```

**Output**:
```
❌ get_crypto_price failed
✅ collect_crypto_data works
❌ get_latest_news failed
✅ collect_news works
✅ get_plugin_status works
❌ get_network_metrics failed
❌ get_weather_data failed
❌ get_tefas_funds failed
```

## Architecture Gap Analysis

### Current Flow (Broken)
```
OpenWebUI → API Gateway (/v1/ai/functions/{tool}) → Plugin Registry (/v1/plugins/{name}/analysis) → ❌ 404
```

### Expected Flow (Needed)
```
OpenWebUI → API Gateway (/v1/ai/functions/{tool}) → ???

Options:
1. Plugin Registry (/v1/plugins/{name}/analysis) - CREATE THESE ENDPOINTS
2. Database Query (PostgreSQL) - QUERY COLLECTED DATA DIRECTLY
3. Data Service (new) - CREATE DEDICATED DATA ACCESS SERVICE
```

## Recommendations

### Option 1: Create Analysis Endpoints in Plugin Registry ⭐ **RECOMMENDED**

**Pros**:
- Maintains current architecture
- Plugins own their data access logic
- Consistent API surface

**Implementation**:
- Add `/v1/plugins/{name}/analysis` endpoints to each plugin
- Endpoints query plugin's PostgreSQL database for latest collected data
- Return analyzed/sentiment data in structured format

**Example for crypto plugin**:
```python
@router.get("/v1/plugins/{plugin_name}/analysis")
async def get_analysis(plugin_name: str, symbol: str = None, limit: int = 10):
    """Return latest analyzed data for plugin"""
    # Query plugin's database for collected data
    # Apply analysis/sentiment if needed
    # Return structured response
```

### Option 2: Direct Database Queries

**Pros**:
- Fastest implementation
- Direct data access

**Cons**:
- API Gateway needs database credentials
- Tight coupling to database schema
- Bypasses plugin abstraction layer

### Option 3: Create Data Service

**Pros**:
- Separates concerns (collection vs. access)
- Can cache results
- Can provide unified data format

**Cons**:
- New service to maintain
- Additional infrastructure

## Next Steps

1. **Immediate**: Choose implementation approach (recommend Option 1)
2. **Short-term**: Implement missing `/analysis` endpoints in Plugin Registry
3. **Test**: Re-run tool execution tests after implementation
4. **Document**: Update API documentation with available endpoints

## Conclusion

The tool execution infrastructure is partially functional but has a critical architectural gap. The "collect" functions work correctly, but the "get" functions fail because they reference non-existent analysis endpoints. This needs to be resolved before OpenWebUI can successfully call these tools in production.

**Test Status**: **DONE_WITH_CONCERNS** - Tests completed but architectural issues identified that must be addressed.
