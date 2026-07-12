# services/plugin-state-manager/main.py
"""
Plugin State Manager Service
Central plugin management, state control, and AI tools execution
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

from core.database import close_db_pool, get_db_pool, initialize_database
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import licensing, state, tools

# Shared library (needs src/ on the path)
sys.path.insert(0, "/app/src")
from shared.config import MinderBaseSettings  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402

# ============================================================================
# Settings
# ============================================================================


class Settings(MinderBaseSettings):
    """Plugin State Manager settings.

    Inherits common fields + the required-secret contract (DB_PASSWORD,
    REDIS_PASSWORD, JWT_SECRET) from shared.config.MinderBaseSettings; only the
    service-specific overrides live here.
    """

    APP_NAME: str = "Plugin State Manager"
    VERSION: str = "2.1.0"
    PORT: int = 8003
    DB_NAME: str = "minder_marketplace"


settings = Settings()

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.plugin-state-manager")


# ============================================================================
# FastAPI Application
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"🚀 {settings.APP_NAME} v{settings.VERSION} starting...")
    logger.info(f"   Environment: {settings.ENVIRONMENT}")
    logger.info(
        f"   Database: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
    )

    # Initialize database pool
    await get_db_pool()

    # Initialize database schema
    await initialize_database()

    # Load default plugins
    from core.default_plugins import bootstrap_default_plugins

    await bootstrap_default_plugins()

    logger.info(f"✅ {settings.APP_NAME} started successfully")

    yield

    # Shutdown
    logger.info(f"🛑 Shutting down {settings.APP_NAME}...")
    await close_db_pool()
    logger.info(f"✅ {settings.APP_NAME} stopped")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="Central plugin management and AI tools execution",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    pool = await get_db_pool()
    return {
        "service": "plugin-state-manager",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": "connected" if pool else "disconnected",
    }


# ============================================================================
# Include Routers
# ============================================================================

app.include_router(state.router, prefix="/v1/plugins", tags=["State Management"])
app.include_router(
    tools.router, prefix="/v1/tools", tags=["Tool Discovery & Execution"]
)
app.include_router(licensing.router, prefix="/v1/licensing", tags=["Licensing"])


# ============================================================================
# Startup Event
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True if settings.ENVIRONMENT == "development" else False,
        log_level=settings.LOG_LEVEL.lower(),
    )
