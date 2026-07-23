"""
Minder API Gateway
Central entry point for all API requests
Handles authentication, rate limiting, request routing, and logging
"""

import logging
from contextlib import asynccontextmanager

from core.auth import close_pg_pool, init_users_table
from core.clients import SERVICE_REGISTRY, http_client, redis_client
from core.middleware import register_middleware
from fastapi import FastAPI
from routes.ai import router as ai_router
from routes.auth import router as auth_router
from routes.health import router as health_router
from routes.proxy import router as proxy_router

from config import settings

# Configure logging
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.api-gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events"""
    # Startup
    logger.info("API Gateway starting...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Service Registry: {SERVICE_REGISTRY}")

    # Ensure the auth schema exists. This MUST run here, not in an
    # @app.on_event("startup") handler — FastAPI ignores on_event handlers when a
    # lifespan is provided, which previously left the `users` table uncreated and
    # broke register/login on a clean install.
    try:
        await init_users_table()
        logger.info("Auth system initialized")
    except Exception as e:
        logger.error(f"Failed to initialize auth system: {e}")

    yield

    # Shutdown
    logger.info("API Gateway shutting down...")
    try:
        await close_pg_pool()
        logger.info("Auth database connections closed")
    except Exception as e:
        logger.error(f"Failed to close auth connections: {e}")
    await http_client.aclose()
    redis_client.close()


# Configure API documentation based on environment.
# Disable docs in production for security.
if settings.ENVIRONMENT == "production":
    docs_config = {
        "docs_url": None,  # Disable Swagger UI
        "redoc_url": None,  # Disable ReDoc
    }
else:
    docs_config = {
        "docs_url": "/docs",  # Enable in development
        "redoc_url": "/redoc",
    }

# Initialize FastAPI app
app = FastAPI(
    title="Minder API Gateway",
    description="Central API Gateway for Minder Platform",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    **docs_config,
)

# Middleware: CORS, request-id/metrics, rate limiting
register_middleware(app)

# Routers: AI integration, auth, health/metrics, downstream proxy
app.include_router(ai_router)
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(proxy_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)  # nosec: B104
