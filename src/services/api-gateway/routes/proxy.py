"""Downstream proxy routes (plugin-registry, rag-pipeline, model-management).

A plain APIRouter using module-level shared clients (clients.http_client +
SERVICE_REGISTRY); write operations on /v1/plugins/* require a valid JWT.
"""

import logging
from typing import Any, Dict, Optional

import httpx
from core.auth import verify_jwt_token
from core.clients import SERVICE_REGISTRY, http_client
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from config import settings

logger = logging.getLogger("minder.api-gateway")

router = APIRouter()

_MAX_PROXY_BODY_BYTES = settings.MAX_PROXY_BODY_SIZE_MB * 1024 * 1024


async def _read_body_capped(request: Request, max_bytes: int) -> bytes:
    """Read the request body without ever buffering more than max_bytes+1.

    Reading via request.body() has no size limit, so a large upload gets
    fully materialized in memory before we can reject it -- this reads via
    request.stream() instead and bails the moment the cap is exceeded,
    bounding worst-case memory regardless of what (or whether) the client's
    Content-Length header claims.
    """
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Request body exceeds the {settings.MAX_PROXY_BODY_SIZE_MB}MB proxy limit",
            )
        chunks.append(chunk)
    return b"".join(chunks)


# Hop-by-hop headers (RFC 7230 §6.1) that must never be forwarded by a proxy in
# EITHER direction.
_HOP_BY_HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

# Downstream response headers that must NOT be copied onto our re-serialized
# JSONResponse. We rebuild the body from response.json(), so the downstream's
# content framing is stale/wrong: content-length no longer matches, and httpx has
# already transparently decoded any content-encoding (so forwarding "gzip" would
# mislabel a now-plaintext body).
_STRIPPED_RESPONSE_HEADERS = _HOP_BY_HOP_HEADERS | {
    "content-length",
    "content-encoding",
}

# Headers stripped from the OUTBOUND request. Beyond the hop-by-hop set: "host"
# (must reflect the downstream, not the gateway's own inbound Host) and
# "content-length" -- proxy_request always forwards the already-fully-buffered
# body via `content=body` (see _read_body_capped), so httpx computes its own
# correct Content-Length from those exact bytes regardless. Forwarding
# "transfer-encoding" used to be the one hop-by-hop header NOT stripped here: a
# chunk-encoded inbound request (no Content-Length of its own, by definition)
# kept that header verbatim, so httpx's own auto-added Content-Length (computed
# from the buffered body, since none was supplied) landed in the SAME outbound
# request alongside the stale "transfer-encoding: chunked" -- a Content-Length +
# Transfer-Encoding conflict RFC 7230 §3.3.3 forbids, and the exact request-
# smuggling primitive that header pair enables. Confirmed live: a request built
# this way put both headers on the wire and a receiving server reading
# Content-Length bytes got the literal chunk-size line plus truncated JSON.
_STRIPPED_REQUEST_HEADERS = _HOP_BY_HOP_HEADERS | {"host", "content-length"}

# Model pulls, RAG document ingestion, TTS/STT synthesis, and knowledge-graph
# construction can legitimately take minutes (multi-GB Ollama downloads,
# embedding a large document, synthesizing long audio, spaCy NER + Neo4j
# writes) -- the shared http_client's 30s default (core/clients.py) is tuned
# for the fast control-plane calls (plugin-registry/marketplace/plugin-state-
# manager) and was silently killing these with a misleading 504 well before the
# backend actually finished. Confirmed live against model-management's
# register_model, which blocks on a synchronous, non-streamed Ollama pull.
_LONG_OPERATION_TIMEOUT = httpx.Timeout(300.0, connect=10.0)


def _safe_response_headers(headers) -> dict:
    """Drop content-framing + hop-by-hop headers before re-emitting a response."""
    return {
        k: v for k, v in headers.items() if k.lower() not in _STRIPPED_RESPONSE_HEADERS
    }


async def proxy_request(
    service_url: str,
    path: str,
    request: Request,
    *,
    timeout: Optional[httpx.Timeout] = None,
):
    """Proxy request to downstream service.

    `timeout` overrides the shared http_client's 30s default for routes whose
    backend work can legitimately run long (see _LONG_OPERATION_TIMEOUT above).
    Left unset (not passed as an explicit `None` to httpx.request, which would
    mean "no timeout at all" rather than "use the client's default") so the
    normal control-plane routes keep the client's own configured timeout.
    """
    # Build target URL (handle trailing slash properly)
    if path:
        target_url = f"{service_url}/{path}"
    else:
        target_url = service_url

    # Get request body (capped -- see _read_body_capped)
    body = await _read_body_capped(request, _MAX_PROXY_BODY_BYTES)

    # Build headers (excluding hop-by-hop + content-framing headers -- see
    # _STRIPPED_REQUEST_HEADERS)
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _STRIPPED_REQUEST_HEADERS
    }
    headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
    headers["X-Request-ID"] = request.state.request_id

    # multi_items() (not the plain Mapping .items() that a bare QueryParams
    # object's __iter__/dict-conversion would use) -- repeated query keys
    # (?tag=a&tag=b) otherwise silently collapse to just the last value, since
    # httpx's QueryParams constructor falls into a generic-Mapping code path
    # for anything that merely duck-types as a Mapping.
    request_kwargs: Dict[str, Any] = dict(
        method=request.method,
        url=target_url,
        headers=headers,
        content=body,
        params=request.query_params.multi_items(),
    )
    if timeout is not None:
        request_kwargs["timeout"] = timeout

    # Proxy request
    try:
        response = await http_client.request(**request_kwargs)

        # Non-JSON bodies (e.g. tts-stt's synthesized WAV/MP3 audio) must pass
        # through as raw bytes, not be force-decoded as JSON -- response.json()
        # on binary audio raises, which the broad except below would otherwise
        # turn into a misleading 500 "Internal proxy error".
        content_type = response.headers.get("content-type", "")
        if response.content and "application/json" not in content_type:
            return Response(
                status_code=response.status_code,
                content=response.content,
                media_type=content_type or None,
                headers=_safe_response_headers(response.headers),
            )

        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if response.content else None,
            headers=_safe_response_headers(response.headers),
        )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Downstream service timeout")
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Downstream service unreachable")
    except Exception as e:
        logger.error(f"Proxy error: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal proxy error")


def _require_jwt_for_writes(request: Request) -> None:
    """Require a valid JWT for mutating methods; reads pass through.

    Applied uniformly to every proxied service so writes to rag-pipeline and
    model-management (ingest, model pull/delete, …) can no longer be made
    unauthenticated — closing the gap where only /v1/plugins/* was guarded
    (#47). GET stays open for now; tightening reads is a separate policy call.
    """
    if request.method not in ("POST", "PUT", "DELETE", "PATCH"):
        return
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = auth_header.split(" ")[1]
    # verify_jwt_token raises HTTPException(401) on an invalid/expired token.
    request.state.user = verify_jwt_token(token)


# ============================================================================
# Plugin Registry
# ============================================================================


@router.get("/v1/plugins")
async def list_plugins(request: Request):
    """Proxy GET /v1/plugins to Plugin Registry"""
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, "v1/plugins", request)


@router.api_route(
    "/v1/plugins/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_plugin_registry(path: str, request: Request):
    """
    Proxy all /v1/plugins/* requests to Plugin Registry service
    Authentication required for POST/PUT/DELETE/PATCH methods
    """
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, f"v1/plugins/{path}", request)


# ============================================================================
# Bundles (plugin-registry's bundle control-plane)
# ============================================================================


@router.get("/v1/bundles")
async def list_bundles(request: Request):
    """Proxy GET /v1/bundles to Plugin Registry"""
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, "v1/bundles", request)


@router.api_route("/v1/bundles/{path:path}", methods=["GET", "POST"])
async def proxy_to_bundles(path: str, request: Request):
    """Proxy /v1/bundles/* (enable/disable/reconcile) to Plugin Registry.
    Plugin Registry's own routes already carry the full `/v1/bundles/...`
    prefix, so forward the full path back, not just `path` (writes require JWT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, f"v1/bundles/{path}", request)


@router.api_route("/v1/containers/{path:path}", methods=["GET"])
async def proxy_to_containers(path: str, request: Request):
    """Proxy /v1/containers/* (recent container logs, for the Status page) to
    Plugin Registry -- JWT-gated there (not here), since a log read is
    sensitive but this route only carries GETs, which _require_jwt_for_writes
    never gates."""
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, f"v1/containers/{path}", request)


# ============================================================================
# Backups (plugin-registry's backup/restore job queue, #870)
# ============================================================================


@router.api_route("/v1/backups", methods=["GET", "POST"])
async def proxy_to_backups_root(request: Request):
    """Proxy /v1/backups (list archives, enqueue a backup job) to Plugin
    Registry -- admin-gated there (not here), same split as containers/bundles."""
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, "v1/backups", request)


@router.api_route("/v1/backups/{path:path}", methods=["GET", "POST"])
async def proxy_to_backups(path: str, request: Request):
    """Proxy /v1/backups/* (job listing/status, enqueue a restore job) to Plugin
    Registry -- admin-gated there (not here), same split as containers/bundles."""
    service_url = SERVICE_REGISTRY["plugin_registry"]
    return await proxy_request(service_url, f"v1/backups/{path}", request)


# ============================================================================
# RAG Pipeline
# ============================================================================


@router.api_route(
    "/v1/rag/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_rag_pipeline(path: str, request: Request):
    """Proxy all /v1/rag/* requests to RAG Pipeline service (writes require JWT).

    Long timeout: document ingestion/embedding can run well past the shared
    client's 30s default (see _LONG_OPERATION_TIMEOUT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["rag_pipeline"]
    return await proxy_request(
        service_url, path, request, timeout=_LONG_OPERATION_TIMEOUT
    )


# ============================================================================
# Model Management
# ============================================================================


@router.api_route("/v1/models", methods=["GET", "POST"])
async def model_management_root(request: Request):
    """List (GET) or pull (POST) models.

    `/v1/models` maps to the service's `/models` resource, removing the old
    `/v1/models/models` doubling — the gateway prefix and the resource collided because
    the service is *named* "models" (#147/C1).

    Long timeout: a model pull (POST) blocks on a synchronous, non-streamed
    Ollama download that routinely takes minutes for multi-GB models (see
    _LONG_OPERATION_TIMEOUT).
    """
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["model_management"]
    return await proxy_request(
        service_url, "models", request, timeout=_LONG_OPERATION_TIMEOUT
    )


@router.api_route(
    "/v1/models/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_model_management(path: str, request: Request):
    """Proxy `/v1/models/{id}[/...]` to the service's `/models/{id}[/...]` (writes
    require JWT). The gateway prepends the `models/` resource segment so callers use a
    clean `/v1/models/{id}` instead of `/v1/models/models/{id}` (#147/C1).

    Long timeout: `.../test` runs blocking LLM inference and a delete can take a
    while freeing a large model's disk space (see _LONG_OPERATION_TIMEOUT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["model_management"]
    return await proxy_request(
        service_url, f"models/{path}", request, timeout=_LONG_OPERATION_TIMEOUT
    )


# ============================================================================
# Marketplace
# ============================================================================


@router.api_route(
    "/v1/marketplace/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_marketplace(path: str, request: Request):
    """Proxy all /v1/marketplace/* requests to the Marketplace service (writes
    require JWT). Marketplace's own routes already carry the full
    `/v1/marketplace/...` prefix (like plugin_registry, unlike rag_pipeline's
    unversioned aliases) — forward the full path back, not just `path`."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["marketplace"]
    return await proxy_request(service_url, f"v1/marketplace/{path}", request)


@router.api_route(
    "/v1/graph/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_marketplace_graph(path: str, request: Request):
    """Proxy /v1/graph/* (the plugin dependency/conflict/recommendation graph) to
    the Marketplace service -- a second, disjoint route namespace it exposes
    alongside /v1/marketplace/* (writes require JWT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["marketplace"]
    return await proxy_request(service_url, f"v1/graph/{path}", request)


# ============================================================================
# TTS/STT
# ============================================================================


@router.api_route("/v1/tts/{path:path}", methods=["GET", "POST"])
async def proxy_to_tts(path: str, request: Request):
    """Proxy /v1/tts/* to the TTS/STT service (writes require JWT). Synthesis
    (`POST /v1/tts`) returns binary WAV/MP3, not JSON -- proxy_request already
    passes non-JSON bodies through raw.

    Long timeout: synthesizing longer text can take a while (see
    _LONG_OPERATION_TIMEOUT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(
        service_url, f"v1/tts/{path}", request, timeout=_LONG_OPERATION_TIMEOUT
    )


@router.api_route("/v1/tts", methods=["POST"])
async def tts_root(request: Request):
    """Proxy POST /v1/tts (no trailing path) -- {path:path} above requires at
    least one path segment after /v1/tts/, so the bare synthesis call needs its
    own route, mirroring the /v1/models root-route pattern.

    Long timeout: see proxy_to_tts."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(
        service_url, "v1/tts", request, timeout=_LONG_OPERATION_TIMEOUT
    )


@router.api_route("/v1/stt/{path:path}", methods=["GET", "POST"])
async def proxy_to_stt(path: str, request: Request):
    """Proxy /v1/stt/* to the TTS/STT service (writes require JWT).

    Long timeout: transcribing longer audio can take a while (see
    _LONG_OPERATION_TIMEOUT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(
        service_url, f"v1/stt/{path}", request, timeout=_LONG_OPERATION_TIMEOUT
    )


@router.api_route("/v1/stt", methods=["POST"])
async def stt_root(request: Request):
    """Proxy POST /v1/stt (no trailing path) -- multipart audio upload, same
    root-route need as /v1/tts above.

    Long timeout: see proxy_to_stt."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(
        service_url, "v1/stt", request, timeout=_LONG_OPERATION_TIMEOUT
    )


# ============================================================================
# Graph RAG (knowledge-graph construction/retrieval -- distinct from
# marketplace's /v1/graph/* dependency graph above)
# ============================================================================


@router.api_route(
    "/v1/graph-rag/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_graph_rag(path: str, request: Request):
    """Proxy /v1/graph-rag/* to the Graph RAG service's own /v1/* routes (writes
    require JWT). Graph RAG's real paths are unprefixed (`/v1/extract`,
    `/v1/construct-graph`, `/v1/retrieve`, `/v1/entity-context`,
    `/v1/graph/document/{id}`) -- the gateway adds the `graph-rag/` segment so
    this doesn't collide with marketplace's own `/v1/graph/*` proxy above.

    Long timeout: construct-graph runs spaCy NER + several Neo4j writes per
    document (see _LONG_OPERATION_TIMEOUT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["graph_rag"]
    return await proxy_request(
        service_url, f"v1/{path}", request, timeout=_LONG_OPERATION_TIMEOUT
    )


# ============================================================================
# Tool Discovery & Execution (plugin-state-manager)
# ============================================================================


@router.get("/v1/tools")
async def list_tools(request: Request):
    """Proxy GET /v1/tools to Plugin State Manager"""
    service_url = SERVICE_REGISTRY["plugin_state_manager"]
    return await proxy_request(service_url, "v1/tools", request)


@router.api_route("/v1/tools/{path:path}", methods=["GET", "POST"])
async def proxy_to_tools(path: str, request: Request):
    """Proxy /v1/tools/* (tool detail, `POST .../execute`, license `validate`) to
    Plugin State Manager -- a deliberately separate prefix from
    /v1/plugins/{path:path} above (which already routes to plugin-registry) so
    the two services' plugin-adjacent APIs don't collide at the gateway."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["plugin_state_manager"]
    return await proxy_request(service_url, f"v1/tools/{path}", request)
