"""
System endpoints
Handles health checks and system status
"""

import logging

from fastapi import APIRouter, HTTPException, Response
from prometheus_client import REGISTRY, Counter, Histogram, generate_latest

from ..models import HealthResponse, SystemStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System"])

# Prometheus metrics - lazy initialization to avoid duplicates
_request_count = None
_request_duration = None
_plugin_health = None
_data_collection = None


def get_metrics():
    """Get or create metrics (singleton pattern)"""
    global _request_count, _request_duration, _plugin_health, _data_collection

    if _request_count is None:
        _request_count = Counter("minder_requests_total", "Total requests", ["method", "endpoint", "status"])
        _request_duration = Histogram("minder_request_duration_seconds", "Request duration", ["endpoint"])
        _plugin_health = Counter("minder_plugin_health_checks", "Plugin health checks", ["plugin", "status"])
        _data_collection = Counter(
            "minder_data_collection_total",
            "Data collection operations",
            ["plugin", "operation"],
        )

    return _request_count, _request_duration, _plugin_health, _data_collection


def setup_system_routes(router_param, kernel):
    """Setup system routes with kernel reference"""

    @router.get("/status", response_model=SystemStatusResponse, tags=["system"])
    async def system_status() -> SystemStatusResponse:
        """Get detailed system status"""
        if not kernel:
            raise HTTPException(status_code=503, detail="Kernel not initialized")

        return await kernel.get_system_status()

    @router.get("/health", response_model=HealthResponse, tags=["system"])
    async def health() -> HealthResponse:
        """Health check - publicly accessible"""
        if not kernel:
            raise HTTPException(status_code=503, detail="Kernel not initialized")

        status = await kernel.get_system_status()
        return {
            "status": ("healthy" if status["status"] == "running" else "unhealthy"),
            "system": status,
            "authentication": "enabled",
            "network_detection": "enabled",
        }

    @router.get("/metrics", tags=["system"])
    async def metrics():
        """Prometheus metrics endpoint for monitoring"""
        request_count, request_duration, plugin_health, data_collection = get_metrics()
        return Response(content=generate_latest(REGISTRY), media_type="text/plain")
