"""
AI Gateway endpoints for OpenWebUI integration
Provides OpenAI-compatible API for tool calling
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx
from core.auth import get_current_user_required
from fastapi import APIRouter, Depends, HTTPException, Request

from config import settings
from shared.errors import backend_http_error

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/ai", tags=["ai"])

# Ollama URL from environment or default to local
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://minder-ollama:11434")

# Tool cache (refresh every 60 seconds)
_tools_cache: Optional[Dict] = None
_tools_cache_time: Optional[float] = None
CACHE_TTL = 60  # seconds


def _slugify_pipeline_name(name: str) -> str:
    """Turn a pipeline's display name into a safe function-name suffix.

    Lowercases, collapses any run of non-alphanumeric characters into a single
    underscore, and strips leading/trailing underscores -- e.g. "My KB!" ->
    "my_kb". Falls back to "pipeline" if nothing alphanumeric survives, so
    `ask_<slug>` is never a degenerate `ask_`.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "pipeline"


async def _fetch_pipeline_function_defs() -> List[Dict]:
    """Synthesize one OpenAI function-calling definition per RAG pipeline,
    each callable as ``ask_<slug>`` and dispatched to that pipeline's own
    ``POST /v1/pipeline/{id}/query`` on rag-pipeline.

    This is the chat<->RAG bridge: it lets OpenWebUI's own function-calling
    reach Minder's RAG pipelines the same way it already reaches plugin
    tools, without OpenWebUI (which talks to Ollama directly) needing to
    know rag-pipeline exists. Deliberately a separate source merged into
    get_tool_definitions()'s result below -- a RAG pipeline isn't a plugin
    action, so it stays out of the plugin/marketplace tool-aggregation path
    entirely; only the final list is shared.

    Failure here (rag-pipeline unreachable, bad response) degrades to no
    pipeline tools offered, exactly like get_tool_definitions()'s own
    fallback -- it must never be the reason /functions/definitions 500s.
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.RAG_PIPELINE_URL}/v1/pipeline",
                params={"limit": 200},
                timeout=5.0,
            )
            response.raise_for_status()
            pipelines = response.json().get("items", [])
    except Exception as e:
        logger.error(f"Failed to fetch RAG pipelines for tool definitions: {e}")
        return []

    defs: List[Dict] = []
    seen_slugs: set = set()
    for pipeline in pipelines:
        pipeline_id = pipeline.get("id")
        if not pipeline_id:
            continue
        name = pipeline.get("name") or pipeline_id
        slug = _slugify_pipeline_name(name)
        if slug in seen_slugs:
            # Two pipelines can share a slugified name (e.g. "Docs" vs
            # "docs!") -- disambiguate with an id suffix rather than
            # silently dropping one of them from the tool list.
            slug = f"{slug}_{pipeline_id[:8]}"
        seen_slugs.add(slug)
        defs.append(
            {
                "type": "function",
                "function": {
                    "name": f"ask_{slug}",
                    "description": f"Ask a question using the '{name}' knowledge base.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "question": {
                                "type": "string",
                                "description": "The question to ask.",
                            }
                        },
                        "required": ["question"],
                    },
                },
                "metadata": {
                    "endpoint": f"/v1/pipeline/{pipeline_id}/query",
                    "method": "POST",
                    # _call_plugin_tool defaults to PLUGIN_REGISTRY_URL; this
                    # metadata-driven override is what lets the very same
                    # dispatch helper reach a pipeline on rag-pipeline instead.
                    "base_url": settings.RAG_PIPELINE_URL,
                    # The query response is the full QueryResponse envelope
                    # (answer/sources/confidence/...); a chat tool call wants
                    # just the answer text, not sources echoed back verbatim.
                    "result_field": "answer",
                    "kind": "rag_pipeline",
                },
            }
        )
    return defs


async def get_tool_definitions() -> Dict:
    """
    Fetch tool definitions from Plugin Registry, merged with a synthesized
    "ask this RAG pipeline" definition per pipeline (see
    _fetch_pipeline_function_defs).

    Returns cached definitions if available, otherwise fetches fresh. Both
    sources share the one cache/TTL below rather than each inventing its
    own -- a pipeline rename/add/remove becomes visible to OpenWebUI on the
    same cadence a plugin tool change already does.
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
            plugin_tools = response.json().get("tools", [])
        pipeline_tools = await _fetch_pipeline_function_defs()
        _tools_cache = {"tools": plugin_tools + pipeline_tools}
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


@router.get("/tools/openapi.json")
async def tools_openapi_spec():
    """OpenAPI 3.x spec for Minder's read-only plugin tools (#251).

    Consumable directly as an OpenWebUI "Tool Server" (Settings -> Admin -> Tool
    Servers, type "openapi") so the chat UI's own native tool-calling can invoke
    Minder's plugin tools, not just the gateway's own /v1/ai/chat/completions loop.

    Deliberately narrower than plugin-registry's full API: only GET-method (i.e.
    unauthenticated read-only, #254) tools from get_tool_definitions() are included.
    Anything in this spec becomes freely callable by any model connected through it
    with no further per-request auth, so mutating/admin endpoints must never appear
    here -- this mirrors exactly what get_tool_definitions()/_chat_with_tools() would
    let the model call today, just described in OpenAPI instead of OpenAI-tool JSON
    Schema, and it stays in sync automatically as plugins are added/removed/toggled.
    """
    tools = (await get_tool_definitions()).get("tools", [])
    paths: Dict[str, Dict] = {}
    for tool in tools:
        fn = tool.get("function")
        meta = tool.get("metadata", {})
        if not fn or (meta.get("method") or "POST").upper() != "GET":
            continue
        endpoint = meta.get("endpoint")
        if not endpoint:
            continue
        params_schema = fn.get("parameters") or {}
        properties = params_schema.get("properties") or {}
        required = set(params_schema.get("required") or [])
        parameters = [
            {
                "name": pname,
                "in": "query",
                "required": pname in required,
                "schema": {"type": pschema.get("type", "string")},
                "description": pschema.get("description", ""),
            }
            for pname, pschema in properties.items()
        ]
        paths[endpoint] = {
            "get": {
                "operationId": fn["name"],
                "summary": (fn.get("description") or fn["name"])[:120],
                "description": fn.get("description", ""),
                "parameters": parameters,
                "responses": {"200": {"description": "Successful response"}},
            }
        }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Minder Plugin Tools",
            "description": "Read-only data tools from Minder's active plugins.",
            "version": "1.0.0",
        },
        "servers": [{"url": settings.PLUGIN_REGISTRY_URL}],
        "paths": paths,
    }


async def _call_plugin_tool(
    metadata: Dict,
    *,
    json_body: Optional[Dict] = None,
    params=None,
    auth_header: Optional[str] = None,
) -> Dict:
    """Proxy a tool invocation to its endpoint -- Plugin Registry by default, or
    another service when ``metadata["base_url"]`` overrides it (used by the
    RAG-pipeline tools synthesized in _fetch_pipeline_function_defs).

    Forwards the caller's ``Authorization`` header so JWT-gated actions run
    as the calling user (auth model: propagate the user's JWT). Raises on HTTP error.

    ``metadata["result_field"]``, when set, narrows the JSON response down to
    ``{field: value}`` instead of returning it whole -- a RAG pipeline query
    response carries sources/confidence/etc. alongside the answer text, which
    a chat tool call has no use for and would otherwise dump into the model's
    context verbatim.
    """
    target_url = metadata.get("endpoint")
    if not target_url:
        raise HTTPException(status_code=500, detail="tool missing endpoint metadata")
    base_url = metadata.get("base_url", settings.PLUGIN_REGISTRY_URL)
    url = f"{base_url}{target_url}"
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
        data = response.json()
    result_field = metadata.get("result_field")
    if result_field:
        return {result_field: data.get(result_field)}
    return data


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
    args = _normalize_tool_args(body)
    # GET-method tools (#254 read-only actions) take their arguments as query
    # params, not a JSON body -- _call_plugin_tool branches on metadata["method"]
    # and only forwards `params` for GET requests, silently dropping `json_body`.
    # This endpoint used to always send the caller's body as `json_body` and the
    # URL's own query string as `params`, so every GET tool (get_weather,
    # get_crypto_price, get_fund_price, get_news) called the standard way --
    # POSTing the arguments as a JSON body, exactly how the OpenAI
    # function-calling convention and this endpoint's own /functions/definitions
    # schema imply -- silently forwarded ZERO arguments downstream and 400'd.
    # The internal chat-completions tool loop already gets this right (see
    # `is_get` below it); mirror the same routing here.
    metadata = tool.get("metadata", {})
    is_get = (metadata.get("method") or "POST").upper() == "GET"
    try:
        result = await _call_plugin_tool(
            metadata,
            json_body=None if is_get else args,
            params=args if is_get else request.query_params,
            auth_header=request.headers.get("Authorization"),
        )
    except httpx.HTTPStatusError as e:
        # A downstream 4xx here most commonly means the tool's target moved
        # or disappeared since the cached definition was fetched -- most
        # notably a RAG pipeline deleted/renamed within the last CACHE_TTL
        # seconds now 404s on rag-pipeline. Surface that cleanly instead of
        # letting it bubble into a raw 500 (this endpoint had no error
        # handling at all before, for any tool).
        status = e.response.status_code
        detail = e.response.text.strip()[:500] or f"tool '{function_name}' failed"
        raise HTTPException(status_code=status if status < 500 else 502, detail=detail)
    except HTTPException:
        raise
    except Exception as e:
        raise backend_http_error(e, f"Tool execution ({function_name})")
    return {
        "result": result,
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
        # Ollama rejects a bad request (most commonly a 404 for an uninstalled
        # model) with a 4xx — surface that as a clean client error carrying Ollama's
        # own message, instead of letting raise_for_status() bubble an
        # httpx.HTTPStatusError into the handler's `except Exception` → a sanitized
        # 500 (#578). A 5xx is a genuine backend failure, so leave it to
        # raise_for_status()/backend_http_error below.
        if 400 <= response.status_code < 500:
            detail = "Ollama rejected the request"
            try:
                err = response.json().get("error")
                if err:
                    detail = str(err)
            except Exception:
                pass
            raise HTTPException(status_code=response.status_code, detail=detail)
        response.raise_for_status()
        return response.json()


MAX_TOOL_ITERATIONS = 5
# Cap the tool calls honoured per model turn (#942): MAX_TOOL_ITERATIONS bounds
# the outer loop, but a single (possibly malformed/adversarial) model response
# can carry an arbitrary number of tool_calls, each a downstream request with
# its own timeout — an unbounded fan-out driven by untrusted model output.
MAX_TOOL_CALLS_PER_TURN = 8


def _normalize_tool_args(args: object) -> Dict:
    """Unwrap the argument envelope some models emit.

    Ollama tool_calls should carry flat arguments (``{"coin": "bitcoin"}``), but some
    capable models — notably command-r — wrap them as
    ``{"tool_name": "...", "parameters": {"coin": "bitcoin"}}``. Passing that envelope
    to the plugin action (which expects the flat args) makes the call fail. Unwrap a
    ``parameters`` dict when present so these models' tool calls actually execute. A
    flat, correct args dict is returned unchanged (none of the plugin tools take a
    ``parameters`` argument themselves).
    """
    if isinstance(args, dict) and isinstance(args.get("parameters"), dict):
        return args["parameters"]
    return args if isinstance(args, dict) else {}


def _parse_content_tool_call(content: object, meta_by_name: Dict) -> Optional[Dict]:
    """#250: bounded robustness net for models that emit a tool call as JSON text in
    ``content`` instead of native ``tool_calls`` — e.g. qwen2.5-coder returning
    ``{"name": "get_crypto_price", "arguments": {"coin": "bitcoin"}}`` as content.

    Deliberately narrow to avoid false positives on ordinary prose that happens to
    look JSON-ish: content must parse as a JSON *object* whose ``name`` is an EXACT
    match for one of the tools actually offered this turn. Returns a synthetic
    tool_calls-shaped entry (fed through the same normalize/dispatch path as a real
    tool call) or None if content doesn't match this shape.
    """
    if not isinstance(content, str):
        return None
    try:
        parsed = json.loads(content)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    name = parsed.get("name")
    if not isinstance(name, str) or name not in meta_by_name:
        return None
    return {"function": {"name": name, "arguments": parsed.get("arguments") or {}}}


async def _chat_with_tools(body: Dict, auth_header: Optional[str]) -> Dict:
    """Offer plugin tools to the model and run any tool_calls it makes (opt-in path).

    Streaming isn't supported with the tool loop, so a streaming request falls back
    to a plain passthrough. Tool results (or errors — e.g. a 401 when unauthenticated)
    are fed back so the model can answer; a tool problem never aborts the chat.

    Every return path also stamps `minder_tools_offered`/`minder_tool_calls_made`
    onto the response (#328): a model can answer fluently without ever invoking a
    real tool, and prior to this there was no signal anywhere — log or response —
    to tell that apart from a real tool-backed answer. These fields make it
    observable instead of silent; they don't change what's returned otherwise.
    """
    if body.get("stream"):
        resp = await _ollama_chat(body)
        resp["minder_tools_offered"] = False
        resp["minder_tool_calls_made"] = 0
        return resp

    tools_full = (await get_tool_definitions()).get("tools", [])
    if not tools_full:
        resp = await _ollama_chat(body)
        resp["minder_tools_offered"] = False
        resp["minder_tool_calls_made"] = 0
        return resp

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
    tool_call_count = 0
    for _ in range(MAX_TOOL_ITERATIONS):
        resp = await _ollama_chat({**body, "messages": messages, "tools": ollama_tools})
        message = resp.get("message", {})
        tool_calls = message.get("tool_calls")
        if not tool_calls:
            synthetic = _parse_content_tool_call(message.get("content"), meta_by_name)
            if not synthetic:
                resp["minder_tools_offered"] = True
                resp["minder_tool_calls_made"] = tool_call_count
                if tool_call_count == 0:
                    logger.warning(
                        f"Chat completed without invoking any tool despite "
                        f"{len(tools_full)} tool(s) being offered"
                    )
                return resp
            tool_calls = [synthetic]
        messages.append(message)
        if len(tool_calls) > MAX_TOOL_CALLS_PER_TURN:
            logger.warning(
                f"Model requested {len(tool_calls)} tool calls in one turn; "
                f"honouring the first {MAX_TOOL_CALLS_PER_TURN} and dropping the rest"
            )
            tool_calls = tool_calls[:MAX_TOOL_CALLS_PER_TURN]
        for call in tool_calls:
            tool_call_count += 1
            fn = call.get("function", {})
            name = fn.get("name")
            args = _normalize_tool_args(fn.get("arguments") or {})
            meta = meta_by_name.get(name)
            if not meta:
                content = f"error: unknown tool '{name}'"
            else:
                try:
                    # GET tools (#254 read-only actions) take args as query params, not
                    # a JSON body — _call_plugin_tool branches on metadata["method"],
                    # but the caller must still route args to the right kwarg.
                    is_get = (meta.get("method") or "POST").upper() == "GET"
                    result = await _call_plugin_tool(
                        meta,
                        json_body=None if is_get else args,
                        params=args if is_get else None,
                        auth_header=auth_header,
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
    final = await _ollama_chat({**body, "messages": messages})
    final["minder_tools_offered"] = True
    final["minder_tool_calls_made"] = tool_call_count
    return final


@router.post("/chat/completions")
async def chat_completions(
    request: Request, current_user: dict = Depends(get_current_user_required)
):
    """Chat via Ollama. Plugin function-calling is **opt-in and non-blocking**.

    Requires a valid Minder JWT (#613): unlike every other route in this module
    (read-only tool-discovery metadata, or a tool-execution proxy that forwards the
    caller's own JWT to a downstream endpoint which enforces its own auth), this one
    calls Ollama directly with no other gate anywhere in the request path -- an
    unauthenticated caller could otherwise consume shared inference compute for free.
    OpenWebUI's own chat traffic doesn't go through this route at all (it talks to
    Ollama directly per docker-compose.yml's OLLAMA_BASE_URL); the one real in-repo
    caller (VoicePage.tsx's style-rewrite feature) already gates the feature on being
    logged in and is updated alongside this fix to actually send its token.

    By default this is a plain Ollama `/api/chat` passthrough — byte-identical to the
    previous behaviour for any already-authenticated consumer. Send
    ``"minder_tools": true`` in the body to offer the platform's plugin tools;
    the model's tool_calls are then executed against the plugin action endpoints
    (forwarding the caller's JWT). Even opted-in, any failure in the tool path falls
    back to a plain passthrough, so a tool problem never breaks a chat.
    """
    body = await request.json()
    use_tools = bool(body.pop("minder_tools", False))

    if not use_tools:
        try:
            return await _ollama_chat(body)
        except HTTPException:
            # A clean 4xx from Ollama (e.g. unknown model) — surface as-is, don't
            # re-wrap into a 500 (#578).
            raise
        except Exception as e:
            logger.error(f"Chat completion failed: {e}")
            raise backend_http_error(e, "Chat completion")

    try:
        return await _chat_with_tools(body, request.headers.get("Authorization"))
    except Exception as e:
        # Fall back to a plain passthrough for ANY tool-path failure — incl. a model
        # that doesn't support `tools` (Ollama 400) or a tool bug — so a tool problem
        # never breaks a chat that would otherwise work.
        logger.warning(
            f"Tool-augmented chat failed ({e}); falling back to plain passthrough"
        )
        try:
            return await _ollama_chat(body)
        except HTTPException:
            # The plain retry still got a clean 4xx from Ollama (e.g. the model just
            # doesn't exist) — surface it, don't re-wrap into a 500 (#578).
            raise
        except Exception as e2:
            logger.error(f"Chat completion failed: {e2}")
            raise backend_http_error(e2, "Chat completion")
