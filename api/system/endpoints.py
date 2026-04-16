"""
System endpoints
Handles health checks and system status
"""

from fastapi import APIRouter, HTTPException
import logging

from ..models import HealthResponse, SystemStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["System"])


def setup_system_routes(router, kernel):
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

    return router
