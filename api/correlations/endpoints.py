"""
Correlation endpoints
Handles knowledge graph correlations
"""

from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/correlations", tags=["Knowledge Graph"])


def setup_correlation_routes(router, kernel):
    """Setup correlation routes with kernel reference"""

    @router.get("")
    async def get_correlations():
        """Get all correlations"""
        if not kernel:
            raise HTTPException(status_code=503, detail="Kernel not initialized")

        return await kernel.correlation_engine.get_all_correlations()

    return router
