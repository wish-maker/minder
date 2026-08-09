"""Downstream proxy routes (plugin-registry, rag-pipeline, model-management).

A plain APIRouter using module-level shared clients (clients.http_client +
SERVICE_REGISTRY); write operations on /v1/plugins/* require a valid JWT.
"""

import logging

import httpx
from core.auth import verify_jwt_token
from core.clients import SERVICE_REGISTRY, http_client
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

logger = logging.getLogger("minder.api-gateway")

router = APIRouter()

# Downstream response headers that must NOT be copied onto our re-serialized
# JSONResponse. We rebuild the body from response.json(), so the downstream's
# content framing is stale/wrong: content-length no longer matches, and httpx has
# already transparently decoded any content-encoding (so forwarding "gzip" would
# mislabel a now-plaintext body). The rest are hop-by-hop headers (RFC 7230 §6.1)
# that must never be forwarded by a proxy.
_STRIPPED_RESPONSE_HEADERS = frozenset(
    {
        "content-length",
        "content-encoding",
        "transfer-encoding",
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "upgrade",
    }
)


def _safe_response_headers(headers) -> dict:
    """Drop content-framing + hop-by-hop headers before re-emitting a response."""
    return {
        k: v for k, v in headers.items() if k.lower() not in _STRIPPED_RESPONSE_HEADERS
    }


async def proxy_request(service_url: str, path: str, request: Request):
    """Proxy request to downstream service"""
    # Build target URL (handle trailing slash properly)
    if path:
        target_url = f"{service_url}/{path}"
    else:
        target_url = service_url

    # Get request body
    body = await request.body()

    # Build headers (excluding hop-by-hop headers)
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("connection", None)
    headers["X-Forwarded-For"] = request.client.host if request.client else "unknown"
    headers["X-Request-ID"] = request.state.request_id

    # Proxy request
    try:
        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=request.query_params,
        )

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
# RAG Pipeline
# ============================================================================


@router.api_route(
    "/v1/rag/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_rag_pipeline(path: str, request: Request):
    """Proxy all /v1/rag/* requests to RAG Pipeline service (writes require JWT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["rag_pipeline"]
    return await proxy_request(service_url, path, request)


# ============================================================================
# Model Management
# ============================================================================


@router.api_route("/v1/models", methods=["GET", "POST"])
async def model_management_root(request: Request):
    """List (GET) or pull (POST) models.

    `/v1/models` maps to the service's `/models` resource, removing the old
    `/v1/models/models` doubling — the gateway prefix and the resource collided because
    the service is *named* "models" (#147/C1).
    """
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["model_management"]
    return await proxy_request(service_url, "models", request)


@router.api_route(
    "/v1/models/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_model_management(path: str, request: Request):
    """Proxy `/v1/models/{id}[/...]` to the service's `/models/{id}[/...]` (writes
    require JWT). The gateway prepends the `models/` resource segment so callers use a
    clean `/v1/models/{id}` instead of `/v1/models/models/{id}` (#147/C1)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["model_management"]
    return await proxy_request(service_url, f"models/{path}", request)


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
    passes non-JSON bodies through raw."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(service_url, f"v1/tts/{path}", request)


@router.api_route("/v1/tts", methods=["POST"])
async def tts_root(request: Request):
    """Proxy POST /v1/tts (no trailing path) -- {path:path} above requires at
    least one path segment after /v1/tts/, so the bare synthesis call needs its
    own route, mirroring the /v1/models root-route pattern."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(service_url, "v1/tts", request)


@router.api_route("/v1/stt/{path:path}", methods=["GET", "POST"])
async def proxy_to_stt(path: str, request: Request):
    """Proxy /v1/stt/* to the TTS/STT service (writes require JWT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(service_url, f"v1/stt/{path}", request)


@router.api_route("/v1/stt", methods=["POST"])
async def stt_root(request: Request):
    """Proxy POST /v1/stt (no trailing path) -- multipart audio upload, same
    root-route need as /v1/tts above."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["tts_stt"]
    return await proxy_request(service_url, "v1/stt", request)


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
    this doesn't collide with marketplace's own `/v1/graph/*` proxy above."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY["graph_rag"]
    return await proxy_request(service_url, f"v1/{path}", request)


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
