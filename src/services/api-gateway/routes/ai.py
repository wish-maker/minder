"""
AI Gateway endpoints for OpenWebUI integration
Provides OpenAI-compatible API for tool calling
"""

import json
import logging
import os
from datetime import datetime
from typing import Dict, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request

from config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/ai", tags=["ai"])

# Ollama URL from environment or default to local
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://minder-ollama:11434")

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
            response = await client.get(
                f"{settings.PLUGIN_REGISTRY_URL}/v1/plugins/ai/tools", timeout=5.0
            )
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


async def _call_plugin_tool(
    metadata: Dict,
    *,
    json_body: Optional[Dict] = None,
    params=None,
    auth_header: Optional[str] = None,
) -> Dict:
    """Proxy a tool invocation to its plugin endpoint on the Plugin Registry.

    Forwards the caller's ``Authorization`` header so JWT-gated plugin actions run
    as the calling user (auth model: propagate the user's JWT). Raises on HTTP error.
    """
    target_url = metadata.get("endpoint")
    if not target_url:
        raise HTTPException(status_code=500, detail="tool missing endpoint metadata")
    url = f"{settings.PLUGIN_REGISTRY_URL}{target_url}"
    method = metadata.get("method", "POST")
    headers = {"Authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient() as client:
        if method == "GET":
            response = await client.get(
                url, params=params, headers=headers, timeout=60.0
            )
        else:
            response = await client.post(
                url, json=json_body or {}, headers=headers, timeout=60.0
            )
        response.raise_for_status()
        return response.json()


@router.post("/functions/{function_name}")
async def execute_function(function_name: str, request: Request):
    """Execute a specific AI tool by proxying to its plugin endpoint.

    Forwards the caller's JWT so JWT-gated actions run as the calling user.
    """
    tools_response = await get_tool_definitions()
    tool = next(
        (
            t
            for t in tools_response.get("tools", [])
            if t.get("function", {}).get("name") == function_name
        ),
        None,
    )
    if not tool:
        raise HTTPException(status_code=404, detail=f"Tool {function_name} not found")

    try:
        body = await request.json()
    except Exception:
        body = {}
    result = await _call_plugin_tool(
        tool.get("metadata", {}),
        json_body=body,
        params=request.query_params,
        auth_header=request.headers.get("Authorization"),
    )
    return {
        "result": result,
        "status": "success",
        "timestamp": datetime.now().isoformat(),
    }


async def _ollama_chat(body: Dict) -> Dict:
    """Call Ollama /api/chat and return the single JSON response.

    ``stream`` is forced off: Ollama streams newline-delimited JSON by default, which
    ``response.json()`` cannot parse (it raises "Extra data" on the second line) and
    which the tool loop cannot inspect for ``tool_calls``. This endpoint has always
    aggregated a single response (never proxied a stream), so pinning stream=False is a
    correctness fix, not a behaviour change.
    """
    payload = {**body, "stream": False}
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=120.0
        )
        response.raise_for_status()
        return response.json()


MAX_TOOL_ITERATIONS = 5


async def _chat_with_tools(body: Dict, auth_header: Optional[str]) -> Dict:
    """Offer plugin tools to the model and run any tool_calls it makes (opt-in path).

    Streaming isn't supported with the tool loop, so a streaming request falls back
    to a plain passthrough. Tool results (or errors — e.g. a 401 when unauthenticated)
    are fed back so the model can answer; a tool problem never aborts the chat.
    """
    if body.get("stream"):
        return await _ollama_chat(body)

    tools_full = (await get_tool_definitions()).get("tools", [])
    if not tools_full:
        return await _ollama_chat(body)

    # Ollama wants clean {type, function} defs; keep metadata aside for routing.
    ollama_tools = [
        {"type": t.get("type", "function"), "function": t["function"]}
        for t in tools_full
        if t.get("function")
    ]
    meta_by_name = {
        t["function"]["name"]: t.get("metadata", {})
        for t in tools_full
        if t.get("function")
    }

    messages = list(body.get("messages", []))
    for _ in range(MAX_TOOL_ITERATIONS):
        resp = await _ollama_chat({**body, "messages": messages, "tools": ollama_tools})
        message = resp.get("message", {})
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            return resp
        messages.append(message)
        for call in tool_calls:
            fn = call.get("function", {})
            name = fn.get("name")
            args = fn.get("arguments") or {}
            meta = meta_by_name.get(name)
            if not meta:
                content = f"error: unknown tool '{name}'"
            else:
                try:
                    result = await _call_plugin_tool(
                        meta, json_body=args, auth_header=auth_header
                    )
                    content = json.dumps(result)[:4000]
                except httpx.HTTPStatusError as he:
                    code = he.response.status_code
                    # Feed the downstream error detail back to the model, not just the
                    # status code, so it can self-correct on a later iteration — e.g. a
                    # hallucinated argument yields "bad arguments: got an unexpected
                    # keyword argument 'x'", letting the model retry without it.
                    detail = he.response.text.strip()[:500] or "(no detail)"
                    content = f"error: tool '{name}' returned HTTP {code}: {detail}"
                    if code == 401:
                        content += " (authentication required — sign in to use it)"
                except Exception as te:
                    content = f"error: tool '{name}' failed: {te}"
            messages.append({"role": "tool", "content": content})
    # Iterations exhausted — one final answer without further tool offers.
    return await _ollama_chat({**body, "messages": messages})


@router.post("/chat/completions")
async def chat_completions(request: Request):
    """Chat via Ollama. Plugin function-calling is **opt-in and non-blocking**.

    By default this is a plain Ollama `/api/chat` passthrough — byte-identical to the
    previous behaviour, so no existing consumer (OpenWebUI, plain chat) is affected.
    Send ``"minder_tools": true`` in the body to offer the platform's plugin tools;
    the model's tool_calls are then executed against the plugin action endpoints
    (forwarding the caller's JWT). Even opted-in, any failure in the tool path falls
    back to a plain passthrough, so a tool problem never breaks a chat.
    """
    body = await request.json()
    use_tools = bool(body.pop("minder_tools", False))

    if not use_tools:
        try:
            return await _ollama_chat(body)
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise HTTPException(status_code=502, detail=f"Chat failed: {str(e)}")

    try:
        return await _chat_with_tools(body, request.headers.get("Authorization"))
    except Exception as e:
        logger.warning(
            f"Tool-augmented chat failed ({e}); falling back to plain passthrough"
        )
        try:
            return await _ollama_chat(body)
        except Exception as e2:
            logger.error(f"Chat completion failed: {e2}")
            raise HTTPException(status_code=502, detail=f"Chat failed: {str(e2)}")
