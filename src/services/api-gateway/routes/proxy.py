"""Downstream proxy routes (plugin-registry, rag-pipeline, model-management).

A plain APIRouter using module-level shared clients (clients.http_client +
SERVICE_REGISTRY); write operations on /v1/plugins/* require a valid JWT.
"""

import logging

import httpx
from clients import SERVICE_REGISTRY, http_client
from core.auth import verify_jwt_token
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("minder.api-gateway")

router = APIRouter()


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
    headers["X-Forwarded-For"] = request.client.host
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

        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if response.content else None,
            headers=dict(response.headers),
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
    service_url = SERVICE_REGISTRY.get("plugin_registry")
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
    service_url = SERVICE_REGISTRY.get("plugin_registry")
    return await proxy_request(service_url, f"v1/plugins/{path}", request)


# ============================================================================
# RAG Pipeline
# ============================================================================


@router.api_route(
    "/v1/rag/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_rag_pipeline(path: str, request: Request):
    """Proxy all /v1/rag/* requests to RAG Pipeline service (writes require JWT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY.get("rag_pipeline")
    return await proxy_request(service_url, path, request)


# ============================================================================
# Model Management
# ============================================================================


@router.api_route(
    "/v1/models/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"]
)
async def proxy_to_model_management(path: str, request: Request):
    """Proxy all /v1/models/* requests to Model Management service (writes require JWT)."""
    _require_jwt_for_writes(request)
    service_url = SERVICE_REGISTRY.get("model_management")
    return await proxy_request(service_url, path, request)
