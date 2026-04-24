"""
AI Gateway endpoints for OpenWebUI integration
Provides OpenAI-compatible API for tool calling
"""

import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/ai", tags=["ai"])

# Tool definitions (from functions.json)
TOOLS_DEFINITIONS = {
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_crypto_price",
                "description": "Get current cryptocurrency price and market data",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "enum": ["BTC", "ETH", "SOL", "ADA", "DOT"],
                            "description": "Cryptocurrency symbol",
                        }
                    },
                    "required": ["symbol"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "collect_crypto_data",
                "description": "Trigger cryptocurrency data collection from exchanges",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_latest_news",
                "description": "Get latest news articles with sentiment analysis",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}, "source": {"type": "string"}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "collect_news",
                "description": "Trigger news collection from RSS feeds",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_plugin_status",
                "description": "Get health status of all plugins",
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_network_metrics",
                "description": "Get latest network performance metrics",
                "parameters": {
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "default": 10}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_weather_data",
                "description": "Get latest weather data for configured locations",
                "parameters": {
                    "type": "object",
                    "properties": {"location": {"type": "string", "default": "Istanbul"}},
                    "required": [],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_tefas_funds",
                "description": "Get Turkish investment fund data from TEFAS",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "fund_type": {"type": "string", "default": "YATIRIM"},
                        "limit": {"type": "integer", "default": 10},
                    },
                    "required": [],
                },
            },
        },
    ]
}

# Map function names to Plugin Registry API calls
FUNCTION_MAPPINGS = {
    "get_crypto_price": {"url": "http://minder-plugin-registry:8001/v1/plugins/crypto/analysis", "method": "GET"},
    "collect_crypto_data": {"url": "http://minder-plugin-registry:8001/v1/plugins/crypto/collect", "method": "POST"},
    "get_latest_news": {"url": "http://minder-plugin-registry:8001/v1/plugins/news/analysis", "method": "GET"},
    "collect_news": {"url": "http://minder-plugin-registry:8001/v1/plugins/news/collect", "method": "POST"},
    "get_plugin_status": {"url": "http://minder-plugin-registry:8001/v1/plugins", "method": "GET"},
    "get_network_metrics": {"url": "http://minder-plugin-registry:8001/v1/plugins/network/analysis", "method": "GET"},
    "get_weather_data": {"url": "http://minder-plugin-registry:8001/v1/plugins/weather/analysis", "method": "GET"},
    "get_tefas_funds": {"url": "http://minder-plugin-registry:8001/v1/plugins/tefas/analysis", "method": "GET"},
}


@router.get("/functions/definitions")
async def get_function_definitions():
    """Return available tool definitions for LLM"""
    return TOOLS_DEFINITIONS


@router.post("/functions/{function_name}")
async def execute_function(function_name: str, request: Request):
    """Execute a Minder platform function"""
    params = await request.json()

    if function_name not in FUNCTION_MAPPINGS:
        raise HTTPException(status_code=404, detail=f"Unknown function: {function_name}")

    mapping = FUNCTION_MAPPINGS[function_name]
    url = mapping["url"]
    method = mapping["method"]

    # Call Plugin Registry API
    try:
        async with httpx.AsyncClient() as client:
            if method == "POST":
                response = await client.post(url, json=params, timeout=30.0)
            else:
                # Add query parameters for GET requests
                if params:
                    url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
                response = await client.get(url, timeout=30.0)

            response.raise_for_status()

            return {"result": response.json(), "status": "success", "timestamp": datetime.utcnow().isoformat()}
    except httpx.HTTPError as e:
        logger.error(f"Function execution failed: {e}")
        raise HTTPException(status_code=500, detail=f"Function execution failed: {str(e)}")


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """OpenAI-compatible chat completions endpoint"""
    body = await request.json()

    # For now, route to Ollama
    # TODO: Implement proper function calling flow
    ollama_url = "http://minder-ollama:11434/api/chat"

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(ollama_url, json=body, timeout=120.0)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as e:
        logger.error(f"Chat completion failed: {e}")
        raise HTTPException(status_code=500, detail=f"Chat completion failed: {str(e)}")
