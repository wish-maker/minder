# 🧪 OpenWebUI AI Integration Test Guide

**Purpose:** Verify end-to-end tool calling from OpenWebUI chat interface to Minder Platform APIs

**Last Updated:** 2026-04-23 22:30

---

## 📋 Test Overview

This guide tests the complete flow:
1. User types natural language query in OpenWebUI chat
2. LLM (Llama 3.2) recognizes need for tool
3. LLM calls Minder API via tool definitions
4. Minder API executes the tool
5. Result returned to LLM
6. LLM formats response for user

---

## 🔧 Prerequisites

Before testing, verify:

1. **All services are running:**
```bash
docker compose -f infrastructure/docker/docker-compose.yml ps
```
Expected: 20/20 containers healthy

2. **Ollama has Llama 3.2 model:**
```bash
docker exec minder-ollama ollama list
```
Expected: `llama3.2` in the list

3. **API Gateway is responding:**
```bash
curl http://localhost:8000/health
```
Expected: `{"status": "healthy"}`

4. **AI integration endpoint is accessible:**
```bash
curl http://localhost:8000/v1/ai/status
```
Expected: Returns AI status with available tools

---

## ✅ Step 1: Verify Tool Definitions

**Test:** Check that Minder Platform tool definitions are accessible

```bash
curl http://localhost:8000/v1/ai/functions/definitions
```

**Expected Result:**
```json
{
  "functions": [
    {
      "name": "collect_crypto_data",
      "description": "Collect latest cryptocurrency market data...",
      "parameters": {
        "type": "object",
        "properties": {
          "symbols": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Cryptocurrency symbols..."
          }
        }
      }
    },
    {
      "name": "get_crypto_price",
      "description": "Get current price and market data...",
      ...
    },
    ...
  ]
}
```

**Expected Count:** 8 functions

**Status:** ☐ Pass / ☐ Fail

---

## ✅ Step 2: Test Direct Tool Execution

**Test:** Execute a tool directly via API (bypassing LLM)

### Test 2.1: Get Crypto Price

```bash
curl -X POST http://localhost:8000/v1/ai/functions/get_crypto_price \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC"}'
```

**Expected Result:**
```json
{
  "result": {
    "symbol": "BTC",
    "price": 65000.00,
    "market_cap": 1200000000000,
    "24h_change": 2.5
  },
  "status": "success",
  "timestamp": "2026-04-23T22:30:00Z"
}
```

**Status:** ☐ Pass / ☐ Fail

### Test 2.2: Collect Crypto Data

```bash
curl -X POST http://localhost:8000/v1/ai/functions/collect_crypto_data \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected Result:**
```json
{
  "result": {
    "collected": 5,
    "symbols": ["BTC", "ETH", "SOL", "ADA", "DOT"],
    "sources": ["Binance", "CoinGecko", "Kraken"]
  },
  "status": "success",
  "timestamp": "2026-04-23T22:30:00Z"
}
```

**Status:** ☐ Pass / ☐ Fail

### Test 2.3: Get Latest News

```bash
curl -X POST http://localhost:8000/v1/ai/functions/get_latest_news \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}'
```

**Expected Result:**
```json
{
  "result": {
    "articles": [
      {
        "title": "Bitcoin reaches new high",
        "source": "BBC",
        "sentiment": "positive",
        "published_at": "2026-04-23T20:00:00Z"
      },
      ...
    ],
    "total": 5
  },
  "status": "success",
  "timestamp": "2026-04-23T22:30:00Z"
}
```

**Status:** ☐ Pass / ☐ Fail

### Test 2.4: Get Plugin Status

```bash
curl -X POST http://localhost:8000/v1/ai/functions/get_plugin_status \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Expected Result:**
```json
{
  "result": {
    "plugins": [
      {
        "name": "crypto",
        "enabled": true,
        "health": "healthy"
      },
      {
        "name": "news",
        "enabled": true,
        "health": "healthy"
      },
      ...
    ],
    "total": 5
  },
  "status": "success",
  "timestamp": "2026-04-23T22:30:00Z"
}
```

**Status:** ☐ Pass / ☐ Fail

---

## ✅ Step 3: Test OpenWebUI Integration

**Test:** Verify OpenWebUI can access tool definitions

### Test 3.1: Check functions.json is Mounted

```bash
docker exec minder-openwebui cat /app/config/functions.json
```

**Expected Result:** Valid JSON with 8 function definitions

**Status:** ☐ Pass / ☐ Fail

### Test 3.2: Access OpenWebUI

Open browser: http://localhost:3002

**Expected:** OpenWebUI login page loads

**Status:** ☐ Pass / ☐ Fail

### Test 3.3: Login to OpenWebUI

1. Click "Sign Up" or use default account
2. Enter username: `admin`
3. Enter password: (any 8+ characters for testing)

**Expected:** Successful login, chat interface appears

**Status:** ☐ Pass / ☐ Fail

---

## ✅ Step 4: End-to-End Chat Tests

**Test:** User types natural language queries, LLM calls tools

### Test 4.1: Crypto Price Query

**User Message:**
```
What's the current price of Bitcoin?
```

**Expected Behavior:**
1. LLM recognizes need for `get_crypto_price` tool
2. LLM calls tool with `{"symbol": "BTC"}`
3. Tool returns price data
4. LLM formats response: "Bitcoin is currently trading at $65,000, up 2.5% in the last 24 hours."

**Status:** ☐ Pass / ☐ Fail

**Notes:**
- If LLM doesn't call tool, check tool definitions are loaded
- If tool fails, check API Gateway logs
- If response is generic, LLM may not be receiving tool results

---

### Test 4.2: Crypto Data Collection

**User Message:**
```
Collect the latest crypto data for me
```

**Expected Behavior:**
1. LLM recognizes need for `collect_crypto_data` tool
2. LLM calls tool
3. Tool returns collection results
4. LLM responds: "I've collected data for 5 cryptocurrencies (BTC, ETH, SOL, ADA, DOT) from Binance, CoinGecko, and Kraken."

**Status:** ☐ Pass / ☐ Fail

---

### Test 4.3: News Query

**User Message:**
```
What are the latest news headlines?
```

**Expected Behavior:**
1. LLM recognizes need for `get_latest_news` tool
2. LLM calls tool with `{"limit": 5}`
3. Tool returns news articles
4. LLM summarizes headlines and sentiment

**Status:** ☐ Pass / ☐ Fail

---

### Test 4.4: Plugin Status Query

**User Message:**
```
Check the status of all plugins
```

**Expected Behavior:**
1. LLM recognizes need for `get_plugin_status` tool
2. LLM calls tool
3. Tool returns plugin status
4. LLM reports: "All 5 plugins are healthy and enabled: crypto, news, network, weather, tefas"

**Status:** ☐ Pass / ☐ Fail

---

### Test 4.5: Multi-Tool Query

**User Message:**
```
Give me a summary of the crypto market and latest news
```

**Expected Behavior:**
1. LLM recognizes need for multiple tools
2. LLM calls `get_crypto_price` for BTC/ETH
3. LLM calls `get_latest_news`
4. LLM synthesizes combined response

**Status:** ☐ Pass / ☐ Fail

---

## 🔍 Debugging Failed Tests

### If Tool Definitions Not Loading

**Check 1:** Verify functions.json exists
```bash
ls -la infrastructure/docker/openwebui/functions.json
```

**Check 2:** Verify mount in docker-compose.yml
```bash
grep -A 10 "openwebui:" infrastructure/docker/docker-compose.yml | grep functions.json
```

**Check 3:** Check container has file
```bash
docker exec minder-openwebui ls -la /app/config/functions.json
```

---

### If LLM Doesn't Call Tools

**Problem:** LLM ignores tool definitions

**Solutions:**
1. Check OpenWebUI logs:
```bash
docker logs -f minder-openwebui
```

2. Verify Ollama model supports tool calling:
```bash
docker exec minder-ollama ollama show llama3.2
```

3. Check functions.json format is correct:
```bash
cat infrastructure/docker/openwebui/functions.json | jq .
```

4. Restart OpenWebUI container:
```bash
docker compose -f infrastructure/docker/docker-compose.yml restart openwebui
```

---

### If Tool Execution Fails

**Problem:** LLM calls tool but API returns error

**Check 1:** API Gateway logs
```bash
docker logs -f minder-api-gateway
```

**Check 2:** Plugin Registry logs
```bash
docker logs -f minder-plugin-registry
```

**Check 3:** Test tool directly (see Step 2)
```bash
curl -X POST http://localhost:8000/v1/ai/functions/get_crypto_price \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC"}'
```

---

### If LLM Doesn't Receive Tool Results

**Problem:** Tool executes but LLM gives generic response

**Check 1:** Verify tool response format
```bash
# Tool response must have this structure:
{
  "result": {...},  # Actual data
  "status": "success",
  "timestamp": "2026-04-23T22:30:00Z"
}
```

**Check 2:** Check OpenWebUI can reach API Gateway
```bash
docker exec minder-openwebui curl http://minder-api-gateway:8000/v1/ai/status
```

**Check 3:** Check network connectivity
```bash
docker network inspect minder-network
```

---

## 📊 Test Results Summary

| Step | Test | Status | Notes |
|------|------|--------|-------|
| 1 | Tool definitions accessible | ☐ Pass / ☐ Fail | |
| 2.1 | Get crypto price | ☐ Pass / ☐ Fail | |
| 2.2 | Collect crypto data | ☐ Pass / ☐ Fail | |
| 2.3 | Get latest news | ☐ Pass / ☐ Fail | |
| 2.4 | Get plugin status | ☐ Pass / ☐ Fail | |
| 3.1 | functions.json mounted | ☐ Pass / ☐ Fail | |
| 3.2 | OpenWebUI accessible | ☐ Pass / ☐ Fail | |
| 3.3 | OpenWebUI login | ☐ Pass / ☐ Fail | |
| 4.1 | Crypto price query | ☐ Pass / ☐ Fail | |
| 4.2 | Data collection query | ☐ Pass / ☐ Fail | |
| 4.3 | News query | ☐ Pass / ☐ Fail | |
| 4.4 | Plugin status query | ☐ Pass / ☐ Fail | |
| 4.5 | Multi-tool query | ☐ Pass / ☐ Fail | |

**Overall Status:** ☐ All Pass / ☐ Some Fail / ☐ All Fail

---

## 🎯 Success Criteria

**Integration is working when:**
- ✅ All 8 tool definitions are accessible via API
- ✅ All tools execute successfully when called directly
- ✅ OpenWebUI can access functions.json
- ✅ User can login to OpenWebUI
- ✅ User can type natural language queries
- ✅ LLM calls appropriate tools automatically
- ✅ Tool results are returned to LLM
- ✅ LLM provides formatted responses to user

**If all criteria met:** OpenWebUI AI integration is **COMPLETE** ✅

**If some criteria fail:** See debugging section above

---

## 📝 Next Steps After Testing

### If Tests Pass:
1. ✅ Mark OPENWEBUI-001 as resolved in ISSUES.md
2. ✅ Update CURRENT_STATUS.md to reflect AI integration working
3. ✅ Add example chat screenshots to documentation
4. ✅ Move to next issue: Creating Grafana dashboards

### If Tests Fail:
1. Document specific failures in ISSUES.md
2. Create sub-tasks for each failure
3. Debug and fix systematically
4. Re-test until all pass

---

**Remember:** This is the most critical integration in the platform! If tool calling works, users have a powerful AI assistant. If not, they just have a basic chatbot. 🎯
