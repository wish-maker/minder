"""
Crypto Plugin - FastAPI Microservice
Standalone cryptocurrency analysis plugin with AI tool support
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException
from prometheus_client import Counter, make_asgi_app

from .database import get_db, init_db

# Import plugin router
from .plugin import router

# Configure logging
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("minder.crypto")

# Initialize FastAPI app
app = FastAPI(
    title="Minder Crypto Plugin",
    description="Cryptocurrency market data analysis and AI tools",
    version="1.0.0",
)

# Prometheus metrics
request_counter = Counter("crypto_plugin_requests_total", "Total requests to crypto plugin", ["endpoint", "method"])

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Plugin lifespan management"""
    logger.info("🚀 Starting Crypto Plugin...")

    # Initialize database
    await init_db()

    # Register with Plugin Registry
    await register_with_registry()

    yield

    # Cleanup
    logger.info("🛑 Shutting down Crypto Plugin...")


app.router.lifespan_context = lifespan

# Include plugin routes
app.include_router(router, prefix="/api/v1", tags=["crypto"])


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "crypto-plugin",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
    }


@app.get("/ready")
async def readiness_check():
    """Readiness check - is plugin ready to serve requests?"""
    # Check database connection
    try:
        async for db in get_db():
            await db.fetchval("SELECT 1")
            break
        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail="Database not ready")


async def register_with_registry():
    """Register this plugin with Plugin Registry"""
    import httpx

    registry_url = os.getenv("PLUGIN_REGISTRY_URL", "http://minder-plugin-registry:8001")

    plugin_info = {
        "name": "crypto",
        "version": "1.0.0",
        "description": "Cryptocurrency market data analysis",
        "service_type": "plugin",
        "host": os.getenv("PLUGIN_HOST", "minder-crypto-plugin"),
        "port": int(os.getenv("PLUGIN_PORT", "8002")),
        "health_check_url": "/health",
        "api_base_url": "/api/v1",
        "capabilities": ["price_tracking", "market_analysis"],
        "ai_tools_enabled": True,
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(f"{registry_url}/v1/plugins/register", json=plugin_info, timeout=5.0)
            response.raise_for_status()
            logger.info(f"✅ Registered with Plugin Registry: {response.json()}")
    except Exception as e:
        logger.warning(f"⚠️  Failed to register with Plugin Registry: {e}")
        # Don't fail startup - registration can be retried


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PLUGIN_PORT", "8002")))
