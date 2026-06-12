# services/plugin-state-manager/main.py
"""
Plugin State Manager Service
Central plugin management, state control, and AI tools execution
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic_settings import BaseSettings

from core.database import close_db_pool, get_db_pool, initialize_database
from routes import licensing, state, tools
from services.plugin_state_manager.rate_limiting.rate_limiter import add_rate_limiting
from services.shared.models import HealthCheckResponse
from services.shared.utils.cors import add_cors_middleware
from services.shared.utils.redis_client import create_redis_client_from_settings

logger = logging.getLogger("minder.plugin-state-manager")

# ============================================================================
# Settings
# ============================================================================


class Settings(BaseSettings):
    """Application settings"""

    # Server
    APP_NAME: str = "Plugin State Manager"
    VERSION: str = "2.1.0"
    HOST: str = "127.0.0.1"
    PORT: int = 8003

    # Database
    DB_HOST: str = "postgres"
    DB_PORT: int = 5432
    DB_USER: str = "minder"
    DB_PASSWORD: str = "minder"
    DB_NAME: str = "minder_marketplace"

    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = "minder"

    # Services
    MARKETPLACE_URL: str = "http://minder-marketplace:8002"
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"

    # Security
    JWT_SECRET: str = "dev_jwt_secret_change_me"
    JWT_ALGORITHM: str = "HS256"

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()


# ============================================================================
# FastAPI Application
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info(f"🚀 {settings.APP_NAME} v{settings.VERSION} starting...")
    logger.info(f"   Environment: {settings.ENVIRONMENT}")
    logger.info(f"   Database: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")

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

# ============================================================================
# Rate Limiting Configuration
# ============================================================================

# Add rate limiting middleware for production security
try:
    redis_client = create_redis_client_from_settings(settings)
    add_rate_limiting(app, redis_client)
    logger.info("✅ Rate limiting middleware enabled")
except ConnectionError as e:
    logger.warning(f"⚠️ Rate limiting middleware not available (Redis connection failed): {e}")
    redis_client = None
except Exception as e:
    logger.warning(f"⚠️ Rate limiting middleware not available: {e}")
    redis_client = None

# ============================================================================
# CORS Configuration
# ============================================================================

# Add CORS middleware - permissive for development
add_cors_middleware(
    app,
    allowed_origins=["*"],
    allow_credentials=True,
)


# ============================================================================
# Health Check
# ============================================================================


@app.get("/health", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Health check endpoint

    Returns service health status with database connection info
    """
    pool = await get_db_pool()
    return HealthCheckResponse(
        service=settings.APP_NAME,
        version=settings.VERSION,
        status="healthy",
        checks={"database": "connected" if pool else "disconnected"},
    )


# ============================================================================
# Include Routers
# ============================================================================

app.include_router(state.router, prefix="/v1/plugins", tags=["State Management"])
app.include_router(tools.router, prefix="/v1/tools", tags=["Tool Discovery & Execution"])
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
