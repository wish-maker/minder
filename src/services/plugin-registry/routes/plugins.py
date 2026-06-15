"""
Dynamic Proxy Routes for Plugin Microservices
Handles request forwarding to registered plugin services
"""

import logging
from typing import Dict

import httpx
from fastapi import HTTPException, Request, Response

logger = logging.getLogger("minder.plugin-registry")


class ProxyRouter:
    """Dynamic proxy router for plugin microservices"""

    def __init__(self, services_db: Dict):
        """
        Initialize proxy router

        Args:
            services_db: Dictionary of registered services
        """
        self.services_db = services_db
        self.http_client = None

    async def get_http_client(self):
        """Get or create HTTP client for proxying"""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=50, max_connections=100),
            )
        return self.http_client

    async def forward_request(self, service_name: str, path: str, request: Request) -> Response:
        """
        Forward HTTP request to registered service

        Args:
            service_name: Name of the target service
            path: Request path to forward
            request: Original FastAPI request object

        Returns:
            Response from the target service

        Raises:
            HTTPException 404: If service not found
            HTTPException 503: If service unavailable
        """
        # Check if service is registered
        service = self.services_db.get(service_name)
        if not service:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not registered",
            )

        # Build target URL
        target_url = f"http://{service.host}:{service.port}{path}"

        logger.debug(f"Proxying {request.method} {target_url}")

        try:
            # Get HTTP client
            client = await self.get_http_client()

            # Prepare request data
            body = await request.body()
            headers = dict(request.headers)

            # Remove hop-by-hop headers
            headers.pop("host", None)
            headers.pop("connection", None)
            headers.pop("keep-alive", None)

            # Forward request
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
                params=request.query_params,
            )

            # Return response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except httpx.ConnectError as e:
            logger.error(f"Failed to connect to service {service_name}: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Service '{service_name}' unavailable: connection failed",
            )

        except httpx.TimeoutException:
            logger.error(f"Timeout connecting to service {service_name}")
            raise HTTPException(
                status_code=504,
                detail=f"Service '{service_name}' timeout",
            )

        except Exception as e:
            logger.error(f"Error proxying to {service_name}: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Proxy error: {str(e)}",
            )

    async def health_check_proxy(self, service_name: str) -> Dict:
        """
        Perform health check on registered service

        Args:
            service_name: Name of the service to check

        Returns:
            Health check response from service

        Raises:
            HTTPException 404: If service not found
            HTTPException 503: If health check fails
        """
        service = self.services_db.get(service_name)
        if not service:
            raise HTTPException(
                status_code=404,
                detail=f"Service '{service_name}' not registered",
            )

        try:
            client = await self.get_http_client()
            health_url = f"http://{service.host}:{service.port}{service.health_check_url}"

            response = await client.get(health_url, timeout=5.0)

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=503,
                    detail=f"Service '{service_name}' unhealthy: status {response.status_code}",
                )

        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Service '{service_name}' unreachable",
            )

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail=f"Service '{service_name}' health check timeout",
            )

        except Exception as e:
            logger.error(f"Health check failed for {service_name}: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Health check failed: {str(e)}",
            )

    async def close(self):
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None
