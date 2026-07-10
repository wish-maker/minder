"""Service-discovery and dynamic-proxy endpoints.

Built via a factory so the shared runtime state (services_db, redis client, proxy
router) is injected by ``main`` rather than imported — this keeps the import graph
acyclic and mirrors the modular pattern used elsewhere in the codebase.
"""

import json
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request
from models import ServiceRegistration


def build_services_router(
    *, services_db, redis_client, proxy_router, logger
) -> APIRouter:
    router = APIRouter(tags=["Service Discovery"])

    @router.post("/v1/services/register")
    async def register_service(service: ServiceRegistration):
        """Register a service for service discovery"""
        services_db[service.service_name] = service
        redis_client.hset(
            f"service:{service.service_name}",
            mapping={
                "service_type": service.service_type,
                "host": service.host,
                "port": service.port,
                "health_check_url": service.health_check_url,
                "registered_at": datetime.now().isoformat(),
                "metadata": json.dumps(service.metadata),
            },
        )
        logger.info(f"Service registered: {service.service_name}")
        return {
            "message": f"Service {service.service_name} registered",
            "service": service.dict(),
        }

    @router.get("/v1/services")
    async def list_services():
        """List all registered services"""
        return {"services": list(services_db.values()), "count": len(services_db)}

    @router.get("/v1/services/{service_name}")
    async def get_service(service_name: str):
        """Get service details"""
        service = services_db.get(service_name)
        if not service:
            raise HTTPException(status_code=404, detail="Service not found")
        return service

    @router.delete("/v1/services/{service_name}")
    async def unregister_service(service_name: str):
        """Unregister a service"""
        if service_name not in services_db:
            raise HTTPException(status_code=404, detail="Service not found")
        del services_db[service_name]
        redis_client.delete(f"service:{service_name}")
        return {"message": f"Service {service_name} unregistered"}

    @router.get("/v1/services/{service_name}/health")
    async def check_service_health(service_name: str):
        """Check health of a registered microservice and record it in Redis."""
        try:
            health_data = await proxy_router.health_check_proxy(service_name)
            redis_client.hset(
                f"service:{service_name}",
                mapping={
                    "health_status": "healthy",
                    "last_health_check": datetime.now().isoformat(),
                },
            )
            return {
                "service": service_name,
                "status": "healthy",
                "health_data": health_data,
                "checked_at": datetime.now().isoformat(),
            }
        except HTTPException:
            redis_client.hset(
                f"service:{service_name}",
                mapping={
                    "health_status": "unhealthy",
                    "last_health_check": datetime.now().isoformat(),
                },
            )
            raise

    @router.api_route(
        "/v1/proxy/{service_name}/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "PATCH"],
    )
    async def proxy_to_service(service_name: str, path: str, request: Request):
        """Dynamic proxy: forward a request to a registered microservice."""
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
            "timestamp": datetime.now().isoformat(),
        }

    return router
