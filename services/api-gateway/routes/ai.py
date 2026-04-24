"""
AI Gateway endpoints for OpenWebUI integration
Provides OpenAI-compatible API for tool calling
"""

import logging
from datetime import datetime
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request

from services.api_gateway.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/ai", tags=["ai"])

# Tool cache (refresh every 60 seconds)
_tools_cache: Optional[Dict] = None
_tools_cache_time: Optional[float] = None
CACHE_TTL = 60  # seconds


async def get_tool_definitions() -> Dict:
    """
    Fetch tool definitions from Plugin Registry

    Returns cached definitions if available, otherwise fetches fresh.
    """
    global _tools_cache, _tools_cache_time

    import time

    current_time = time.time()

    # Return cached tools if still fresh
    if _tools_cache and _tools_cache_time:
        if current_time - _tools_cache_time < CACHE_TTL:
            return _tools_cache

    # Fetch fresh tools from Plugin Registry
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{settings.PLUGIN_REGISTRY_URL}/v1/plugins/ai/tools", timeout=5.0)
            response.raise_for_status()
            _tools_cache = response.json()
            _tools_cache_time = current_time
            return _tools_cache
    except Exception as e:
        logger.error(f"Failed to fetch tool definitions: {e}")

        # Return cached tools if available (fallback)
        if _tools_cache:
            logger.warning("Using cached tool definitions due to fetch error")
            return _tools_cache

        # Return empty tools if no cache available
        return {"tools": []}


@router.get("/functions/definitions")
async def get_functions_definitions():
    """
    Get AI tool definitions for OpenWebUI

    Returns aggregated tool definitions from all plugins.
    Fetches dynamically from Plugin Registry.
    """
    return await get_tool_definitions()


@router.post("/functions/{function_name}")
async def execute_function(function_name: str, request: Request):
    """
    Execute a specific AI tool function

    Fetches tool metadata from Plugin Registry and proxies to appropriate plugin endpoint.
    """
    # Get tool definitions to find target endpoint
    tools_response = await get_tool_definitions()

    # Find the requested tool
    tool = None
    for t in tools_response.get("tools", []):
        if t["function"]["name"] == function_name:
            tool = t
            break

    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {function_name} not found")

    # Extract metadata
    metadata = tool.get("metadata", {})
    target_url = metadata.get("endpoint")
    method = metadata.get("method", "POST")

    if not target_url:
        raise HTTPException(status_code=500, detail=f"Tool {function_name} missing endpoint metadata")

    # Build full URL to Plugin Registry
    url = f"{settings.PLUGIN_REGISTRY_URL}{target_url}"

    # Get request body
    body = await request.body()

    # Proxy request to plugin
    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(url, params=request.query_params)
        else:  # POST
            response = await client.post(url, content=body)

        response.raise_for_status()

        # Return result in OpenAI function format
        return {"result": response.json(), "status": "success", "timestamp": datetime.now().isoformat()}


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
