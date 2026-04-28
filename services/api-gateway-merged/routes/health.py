"""
Health Check Routes for Merged API Gateway & Plugin Registry
"""
from fastapi import APIRouter
import asyncio
import sys
from datetime import datetime
from typing import Dict, Any
import redis.asyncio as redis

# Add parent directory to path for imports
sys.path.insert(0, '/app')
from config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """
    Comprehensive health check for merged service
    """
    health_status = {
        "service": "api-gateway-plugin-registry",
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": settings.api_version,
        "environment": settings.environment,
        "checks": {}
    }

    # Check Redis
    try:
        redis_client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password if settings.redis_password else None,
            db=settings.redis_db,
            decode_responses=True
        )
        await redis_client.ping()
        health_status["checks"]["redis"] = "healthy"
        await redis_client.close()
    except Exception as e:
        health_status["checks"]["redis"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check PostgreSQL (using asyncpg directly for simplicity)
    try:
        import asyncpg
        conn = await asyncpg.connect(settings.database_url)
        await conn.fetchval("SELECT 1")
        await conn.close()
        health_status["checks"]["database"] = "healthy"
    except Exception as e:
        health_status["checks"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "unhealthy"

    # Check if overall status is healthy
    if all(v == "healthy" for v in health_status["checks"].values()):
        health_status["status"] = "healthy"
    else:
        health_status["status"] = "unhealthy"

    return health_status


@router.get("/health/ready")
async def readiness_check():
    """
    Readiness check - indicates if service can handle requests
    """
    return {"status": "ready"}


@router.get("/health/live")
async def liveness_check():
    """
    Liveness check - indicates if service is running
    """
    return {"status": "alive"}
