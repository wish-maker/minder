# OpenWebUI - Minder Platform Integration Guide

**Last Updated:** 2026-04-23 22:00
**Purpose:** Enable AI chat interface with tool calling capabilities

---

## Overview

OpenWebUI is configured to work with Minder Platform's Ollama service and should provide:
- Chat interface with Llama 3.2 model
- Tool calling to access Minder APIs
- RAG pipeline integration
- Plugin management from chat

---

## Current Issues

### ❌ Issue 1: OpenWebUI Not Starting

**Root Cause:** Ollama service is unhealthy because no model is running.

**Solution:**
```bash
# Start model in Ollama
docker exec minder-ollama ollama run llama3.2

# Verify model is running
curl http://localhost:11434/api/tags
```

### ❌ Issue 2: No Tool Calling Configuration

OpenWebUI needs to be configured with function calling definitions to call Minder APIs.

**Required:** Create OpenAI-compatible function definitions for:
- Plugin data collection
- Plugin status queries
- Market data queries
- News aggregation

---

## Fixing OpenWebUI Integration

### Step 1: Create Function Definitions

Create `infrastructure/docker/openwebui/functions.json`:

```json
{
  "name": "minder_tools",
  "description": "Minder Platform API tools for data collection and analysis",
  "functions": [
    {
      "name": "collect_crypto_data",
      "description": "Trigger cryptocurrency data collection from Binance, CoinGecko, and Kraken",
      "parameters": {
        "type": "object",
        "properties": {
          "symbol": {
            "type": "string",
            "description": "Cryptocurrency symbol (e.g., BTC, ETH)",
            "enum": ["BTC", "ETH", "SOL", "ADA", "DOT"]
          }
        },
        "required": []
      }
    },
    {
      "name": "get_crypto_price",
      "description": "Get current cryptocurrency price from database",
      "parameters": {
        "type": "object",
        "properties": {
          "symbol": {
            "type": "string",
            "description": "Cryptocurrency symbol (e.g., BTC, ETH)"
          }
        },
        "required": ["symbol"]
      }
    },
    {
      "name": "collect_news",
      "description": "Trigger news aggregation from BBC, Guardian, NPR",
      "parameters": {
        "type": "object",
        "properties": {
          "source": {
            "type": "string",
            "description": "News source",
            "enum": ["BBC", "Guardian", "NPR"]
          }
        },
        "required": []
      }
    },
    {
      "name": "get_latest_news",
      "description": "Get latest news articles from database",
      "parameters": {
        "type": "object",
        "properties": {
          "limit": {
            "type": "integer",
            "description": "Number of articles to return",
            "default": 10
          }
        },
        "required": []
      }
    },
    {
      "name": "get_plugin_status",
      "description": "Get health status of all plugins",
      "parameters": {
        "type": "object",
        "properties": {},
        "required": []
      }
    },
    {
      "name": "enable_plugin",
      "description": "Enable a plugin",
      "parameters": {
        "type": "object",
        "properties": {
          "plugin_name": {
            "type": "string",
            "description": "Plugin name (crypto, news, network, weather, tefas)"
          }
        },
        "required": ["plugin_name"]
      }
    }
  ]
}
```

### Step 2: Update docker-compose.yml

Add OpenWebUI functions configuration:

```yaml
openwebui:
  image: ghcr.io/open-webui/open-webui:main
  container_name: minder-openwebui
  restart: unless-stopped
  environment:
    # Ollama Backend Connection
    - OLLAMA_BASE_URL=http://ollama:11434
    
    # OpenAI Functions (for tool calling)
    - OPENAI_API_KEY=sk-minder-dummy-key
    - OPENAI_BASE_URL=http://minder-api-gateway:8000/v1/ai
    
    # Function definitions
    - ENABLE_FUNCTIONS=true
    - FUNCTIONS_FILE=/app/config/functions.json
  volumes:
    - ./openwebui/functions.json:/app/config/functions.json:ro
```

### Step 3: Create AI Gateway Endpoints

Create `services/api-gateway/routes/ai.py`:

```python
"""
AI Gateway endpoints for OpenWebUI integration
Provides OpenAI-compatible API for tool calling
"""

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse
import httpx
import json
import logging

logger = logging.getLogger(__name__)

@app.post("/v1/ai/chat/completions")
async def chat_completions(request: Request):
    """
    OpenAI-compatible chat completions endpoint
    Routes to Ollama with function calling support
    """
    body = await request.json()
    
    # Extract function calls if present
    messages = body.get("messages", [])
    functions = body.get("functions", [])
    function_call = body.get("function_call", "auto")
    
    # If function calling is requested
    if functions and function_call != "none":
        # For now, return first function (tool use)
        # In production, let LLM decide which function to call
        if functions:
            return {
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "function_call": {
                            "name": functions[0]["name"],
                            "arguments": json.dumps({})
                        }
                    }
                }]
            }
    
    # Otherwise, route to Ollama
    ollama_url = "http://ollama:11434/api/chat"
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            ollama_url,
            json=body,
            timeout=120.0
        )
        return response.json()

@app.post("/v1/ai/functions/{function_name}")
async def execute_function(function_name: str, request: Request):
    """
    Execute Minder platform functions
    Called by OpenWebUI when LLM requests tool use
    """
    params = await request.json()
    
    # Map function names to Minder API calls
    function_mappings = {
        "collect_crypto_data": {
            "url": "http://plugin-registry:8001/v1/plugins/crypto/collect",
            "method": "POST"
        },
        "get_crypto_price": {
            "url": f"http://plugin-registry:8001/v1/plugins/crypto/analysis?symbol={params.get('symbol', 'BTC')}",
            "method": "GET"
        },
        "collect_news": {
            "url": "http://plugin-registry:8001/v1/plugins/news/collect",
            "method": "POST"
        },
        "get_latest_news": {
            "url": f"http://plugin-registry:8001/v1/plugins/news/analysis?limit={params.get('limit', 10)}",
            "method": "GET"
        },
        "get_plugin_status": {
            "url": "http://plugin-registry:8001/v1/plugins",
            "method": "GET"
        },
        "enable_plugin": {
            "url": f"http://plugin-registry:8001/v1/plugins/{params.get('plugin_name')}/enable",
            "method": "POST"
        }
    }
    
    if function_name not in function_mappings:
        raise HTTPException(status_code=404, detail=f"Unknown function: {function_name}")
    
    mapping = function_mappings[function_name]
    url = mapping["url"]
    method = mapping["method"]
    
    # Call Minder API
    async with httpx.AsyncClient() as client:
        if method == "POST":
            response = await client.post(url, json=params)
        else:
            response = await client.get(url)
        
        return response.json()
```

---

## Testing the Integration

### Test 1: Start Ollama with Model

```bash
# Pull and run model
docker exec minder-ollama ollama pull llama3.2
docker exec minder-ollama ollama run llama3.2 &

# Verify
curl http://localhost:11434/api/tags
```

### Test 2: Start OpenWebUI

```bash
cd infrastructure/docker
docker compose up -d openwebui
```

### Test 3: Access Chat Interface

Open browser: http://localhost:8080

### Test 4: Use Tool Calling

In chat interface, say:
```
"Can you collect the latest crypto data?"
```

Expected behavior:
1. OpenWebUI recognizes function call request
2. Calls Minder API Gateway
3. API Gateway triggers plugin data collection
4. Returns results to LLM
5. LLM formats response for user

---

## Required Changes Summary

### Files to Create:
1. `infrastructure/docker/openwebui/functions.json` - Function definitions
2. `services/api-gateway/routes/ai.py` - AI gateway endpoints

### Files to Modify:
1. `infrastructure/docker/docker-compose.yml` - Add OpenWebUI functions config
2. `services/api-gateway/main.py` - Import AI routes

### Environment Variables to Add:
```bash
OPENAI_API_KEY=sk-minder-dummy-key
ENABLE_FUNCTIONS=true
FUNCTIONS_FILE=/app/config/functions.json
```

---

## Alternative: Direct Ollama Integration

If OpenWebUI doesn't work with custom functions, use direct Ollama integration:

### Option A: Ollama Python Library

```python
import ollama

# Initialize
ollama.pull('llama3.2')

# Define tools
tools = [{
    "type": "function",
    "function": {
        "name": "collect_crypto_data",
        "description": "Collect crypto data from Minder Platform",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string"}
            }
        }
    }
}]

# Chat with tools
response = ollama.chat(
    'llama3.2',
    messages=[{"role": "user", "content": "Get BTC price"}],
    tools=tools
)

# Check if tool call requested
if response.get('message', {}).get('tool_calls'):
    # Execute tool call
    tool_call = response['message']['tool_calls'][0]
    function = tool_call['function']['name']
    arguments = json.loads(tool_call['function']['arguments'])
    
    # Call Minder API
    if function == "collect_crypto_data":
        result = call_minder_api(...)
```

### Option B: Simple Chatbot Interface

Create a simple Flask/FastAPI chat interface that:
1. Accepts user messages
2. Sends to Ollama
3. Detects intent (collect data, get price, etc.)
4. Calls Minder APIs
5. Formats response

---

## Priority Implementation Order

1. ✅ **Fix Ollama** - Start llama3.2 model
2. ⚠️ **Create AI Gateway endpoints** - Implement tool calling
3. ⚠️ **Configure OpenWebUI** - Add function definitions
4. ⚠️ **Test integration** - Verify tool calling works
5. ⚠️ **Create user dashboard** - Grafana dashboards for end users

---

## Next Steps

After fixing OpenWebUI integration:

1. **Create Grafana Dashboards** for end users
2. **Implement AI agent** that can autonomously use tools
3. **Add chat-based plugin management**
4. **Create natural language interface** for data queries

---

**This integration is CRITICAL for making Minder Platform user-friendly and enabling AI-assisted operations.**
