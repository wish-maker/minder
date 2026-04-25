# Plugin AI Tools Architecture Design

**Goal:** Enable plugins to dynamically register and expose their own AI tools to OpenWebUI

**Problem:** Current implementation hardcodes 8 AI tools in API Gateway, violating modularity principles

**Architecture:** Plugin-driven tool registration system

---

## Current Architecture (Limited)

```python
# services/api-gateway/routes/ai.py - HARDCODED
TOOLS_DEFINITIONS = {
    "tools": [
        {"name": "get_crypto_price", ...},  # ❌ Static
        {"name": "get_latest_news", ...},    # ❌ Static
        # ... 8 tools all hardcoded
    ]
}
```

**Problems:**
1. ❌ New plugin requires API Gateway code change
2. ❌ Tight coupling between plugins and API Gateway
3. ❌ Can't add/remove tools dynamically
4. ❌ Violates single responsibility principle
5. ❌ Doesn't scale to 20+ plugins

---

## Proposed Architecture (Plugin-Driven)

### 1. Plugin Manifest Extension

Each plugin declares its AI tools in `manifest.yml`:

```yaml
# src/plugins/crypto/manifest.yml
name: crypto
version: 1.0.0
description: Cryptocurrency market data plugin

# NEW: AI tools declaration
ai_tools:
  - name: get_crypto_price
    description: Get current cryptocurrency price and market data
    type: analysis
    endpoint: /analysis
    method: GET
    parameters:
      symbol:
        type: string
        enum: [BTC, ETH, SOL, ADA, DOT]
        description: Cryptocurrency symbol
        required: true
    response_format:
      price: float
      market_cap: float
      change_24h: float
```

### 2. Plugin Registry API Endpoint

```python
# services/plugin-registry/routes/plugins.py

@router.get("/v1/plugins/ai/tools")
async def get_all_ai_tools():
    """Aggregate AI tools from all plugins"""
    tools = []
    for plugin in plugin_manager.list_all():
        manifest = plugin.load_manifest()
        if manifest.get("ai_tools"):
            for tool in manifest["ai_tools"]:
                tools.append({
                    "name": tool["name"],
                    "plugin": plugin.name,
                    "description": tool["description"],
                    "parameters": tool["parameters"],
                    "endpoint": f"/v1/plugins/{plugin.name}{tool['endpoint']}"
                })
    return {"tools": tools}
```

### 3. API Gateway Dynamic Discovery

```python
# services/api-gateway/routes/ai.py

async def get_tool_definitions():
    """Fetch tool definitions from Plugin Registry"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.PLUGIN_REGISTRY_URL}/v1/plugins/ai/tools"
        )
        return response.json()

# No more hardcoded tools!
```

### 4. Plugin Tool Implementation

```python
# src/plugins/crypto/plugin.py

@router.get("/analysis")
async def get_crypto_analysis(symbol: str):
    """
    Analyze cryptocurrency data and return AI-formatted response
    Called by AI router when LLM requests get_crypto_price tool
    """
    # Query database
    data = await db.query_crypto(symbol)

    # Return AI-friendly format
    return {
        "symbol": symbol,
        "price": data["price"],
        "market_cap": data["market_cap"],
        "change_24h": data["change_24h"],
        "timestamp": datetime.now().isoformat()
    }
```

---

## Benefits

✅ **Modularity:** Plugins own their tools
✅ **Scalability:** Add 100+ plugins without touching API Gateway
✅ **Flexibility:** Each plugin defines custom tool schemas
✅ **Discovery:** Central tool registry via Plugin Registry
✅ **Dynamic:** Tools appear/disappear with plugins
✅ **Single Responsibility:** API Gateway just proxies, doesn't define tools

---

## Implementation Tasks

### Phase 5: Plugin AI Tools Architecture (Tasks 21-25)

**Task 21:** Extend Plugin Manifest Schema
- Add `ai_tools` field to manifest.yml
- Update manifest validation
- Document tool schema format

**Task 22:** Create Plugin Registry Tools Endpoint
- Implement `/v1/plugins/ai/tools` endpoint
- Aggregate tools from all plugin manifests
- Return OpenAI-compatible tool definitions

**Task 23:** Update API Gateway AI Router
- Replace hardcoded tools with dynamic discovery
- Fetch tools from Plugin Registry on startup
- Cache tool definitions (refresh every 60s)

**Task 24:** Migrate Existing Plugins
- Add ai_tools to crypto plugin manifest
- Add ai_tools to news plugin manifest
- Add ai_tools to weather, network, tefas plugins
- Implement /analysis endpoints in each plugin

**Task 25:** Testing & Documentation
- Test dynamic tool discovery
- Verify all 8 tools work via new system
- Update plugin development docs
- Add AI tools to plugin template

---

## Migration Strategy

1. **Backward Compatibility:** Keep hardcoded tools as fallback
2. **Gradual Migration:** Migrate plugins one-by-one
3. **Testing:** Verify each plugin's tools before switching
4. **Documentation:** Update plugin development guide

---

## Success Criteria

- ✅ Plugins can declare AI tools in manifest.yml
- ✅ Plugin Registry aggregates all tools
- ✅ API Gateway discovers tools dynamically
- ✅ All 8 existing tools work via new system
- ✅ New plugins can add tools without API Gateway changes
- ✅ No hardcoded tool definitions in API Gateway

---

**Priority:** HIGH - This is critical for platform scalability and modularity

**Estimated Effort:** 5 tasks (similar complexity to current tasks)

**Dependencies:** Requires Plugin Registry enhancement and plugin manifest updates
