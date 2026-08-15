"""Service-discovery and dynamic-proxy endpoints.

Built via a factory so the shared runtime state (services_db, redis client, proxy
router) is injected by ``main`` rather than imported — this keeps the import graph
acyclic and mirrors the modular pattern used elsewhere in the codebase.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from models import ServiceRegistration

from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error
from shared.pagination import paginate


def build_services_router(
    *, services_db, redis_client, proxy_router, logger
) -> APIRouter:
    router = APIRouter(tags=["Service Discovery"])

    @router.post("/v1/services/register")
    async def register_service(
        service: ServiceRegistration,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Register a service for service discovery (JWT or service token)."""
        # Persist BEFORE mutating in-memory state -- load_services_from_redis()
        # is what repopulates services_db on restart, so a Redis failure here
        # must not leave services_db (and this 200 response) claiming a
        # registration that never actually landed in the durable store.
        try:
            redis_client.hset(
                f"service:{service.service_name}",
                mapping={
                    "service_type": service.service_type,
                    "host": service.host,
                    "port": service.port,
                    "health_check_url": service.health_check_url,
                    "registered_at": datetime.now(timezone.utc).isoformat(),
                    "metadata": json.dumps(service.metadata),
                },
            )
        except Exception as e:
            logger.error(f"Failed to persist service {service.service_name}: {e}")
            raise backend_http_error(e, "Service registration")
        services_db[service.service_name] = service
        logger.info(f"Service registered: {service.service_name}")
        return {
            "message": f"Service {service.service_name} registered",
            "service": service.model_dump(),
        }

    @router.get("/v1/services")
    async def list_services(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        """List all registered services, paginated (#147/C6)."""
        page, total = paginate(list(services_db.values()), limit, offset)
        return {
            "services": page,
            "count": len(page),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @router.get("/v1/services/{service_name}")
    async def get_service(service_name: str):
        """Get service details"""
        service = services_db.get(service_name)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        return service

    @router.delete("/v1/services/{service_name}")
    async def unregister_service(
        service_name: str,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Unregister a service (JWT or service token)."""
        if service_name not in services_db:
            raise HTTPException(status_code=404, detail="Service not found")
        # Same persist-before-mutate ordering as register_service above.
        try:
            redis_client.delete(f"service:{service_name}")
        except Exception as e:
            logger.error(f"Failed to unregister service {service_name} in Redis: {e}")
            raise backend_http_error(e, "Service unregistration")
        del services_db[service_name]
        return {"message": f"Service {service_name} unregistered"}

    @router.get("/v1/services/{service_name}/health")
    async def check_service_health(
        service_name: str,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Check health of a registered microservice and record it in Redis.

        Auth-gated: it issues an outbound request to the registered host:port, so
        leaving it open would be an unauthenticated SSRF/health-probe primitive.
        """
        try:
            health_data = await proxy_router.health_check_proxy(service_name)
            redis_client.hset(
                f"service:{service_name}",
                mapping={
                    "health_status": "healthy",
                    "last_health_check": datetime.now(timezone.utc).isoformat(),
                },
            )
            return {
                "service": service_name,
                "status": "healthy",
                "health_data": health_data,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        except HTTPException:
            redis_client.hset(
                f"service:{service_name}",
                mapping={
                    "health_status": "unhealthy",
                    "last_health_check": datetime.now(timezone.utc).isoformat(),
                },
            )
            raise

    @router.api_route(
        "/v1/proxy/{service_name}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    async def proxy_to_service(
        service_name: str,
        path: str,
        request: Request,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Dynamic proxy: forward a request to a registered microservice.

        Auth-gated: this forwards to an arbitrary registered host:port and returns
        the response, so an open version is an SSRF/lateral-movement primitive for
        any in-network caller.
        """
        proxy_path = f"/{path}"
        if request.url.query:
            proxy_path = f"{proxy_path}?{request.url.query}"
        return await proxy_router.forward_request(service_name, proxy_path, request)

    @router.get("/v1/proxy")
    async def list_proxyable_services():
        """List services available for dynamic proxy routing."""
        proxyable = []
        for service_name, service in services_db.items():
            health_status = (
                redis_client.hget(f"service:{service_name}", "health_status")
                or "unknown"
            )
            proxyable.append(
                {
                    "service_name": service_name,
                    "service_type": service.service_type,
                    "health_status": health_status,
                    "endpoint": f"http://{service.host}:{service.port}",
                    "proxy_url": f"/v1/proxy/{service_name}",
                    "metadata": service.metadata,
                }
            )
        return {
            "services": proxyable,
            "count": len(proxyable),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    return router
