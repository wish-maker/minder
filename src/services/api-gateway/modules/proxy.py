"""
Request Proxy Module

Handles proxying requests to downstream services with circuit breaker integration.
"""

import logging

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from .service_registry import ServiceRegistry

logger = logging.getLogger(__name__)


async def proxy_request(
    service_name: str,
    path: str,
    request: Request,
    http_client: httpx.AsyncClient,
    service_registry: ServiceRegistry,
) -> JSONResponse:
    """
    Proxy request to downstream service with circuit breaker and service discovery

    Args:
        service_name: Name of the service to proxy to
        path: Path to append to service URL
        request: Original HTTP request
        http_client: HTTP client for proxying
        service_registry: Service registry instance

    Returns:
        JSONResponse from downstream service

    Raises:
        HTTPException: If service unavailable or request fails
    """
    # Get service URL from registry (with circuit breaker check)
    try:
        service_url = service_registry.get_service_url(service_name)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except HTTPException:
        raise  # Re-raise HTTP exceptions (circuit breaker)

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

    # Proxy request with error handling and circuit breaker tracking
    try:
        response = await http_client.request(
            method=request.method,
            url=target_url,
            headers=headers,
            content=body,
            params=request.query_params,
        )

        # Record successful service call
        service_registry.record_service_call(service_name, True)

        return JSONResponse(
            status_code=response.status_code,
            content=response.json() if response.content else None,
            headers=dict(response.headers),
        )

    except httpx.TimeoutException:
        # Record failed service call
        service_registry.record_service_call(service_name, False)
        raise HTTPException(status_code=504, detail=f"Service {service_name} timeout")
    except httpx.ConnectError as e:
        # Record failed service call
        service_registry.record_service_call(service_name, False)
        logger.error(f"Service {service_name} connection error: {e}")
        raise HTTPException(
            status_code=503, detail=f"Service {service_name} unreachable"
        )
    except Exception as e:
        # Record failed service call
        service_registry.record_service_call(service_name, False)
        logger.error(f"Proxy error for {service_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Internal proxy error: {str(e)}")
