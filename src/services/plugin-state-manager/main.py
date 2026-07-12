# services/plugin-state-manager/main.py
"""
Plugin State Manager Service
Central plugin management, state control, and AI tools execution
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from core.database import close_db_pool, get_db_pool, initialize_database
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import field_validator
from pydantic_settings import BaseSettings
from routes import licensing, state, tools

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
    REDIS_PASSWORD: str  # Required: must be set via environment variable

    @field_validator("REDIS_PASSWORD")
    @classmethod
    def check_redis_password(cls, v: str) -> str:
        if not v:
            raise ValueError("REDIS_PASSWORD must be set via environment variable")
        return v

    # Services
    MARKETPLACE_URL: str = "http://minder-marketplace:8002"
    PLUGIN_REGISTRY_URL: str = "http://minder-plugin-registry:8001"

    # Security
    JWT_SECRET: str  # Required: must be set via environment variable
    JWT_ALGORITHM: str = "HS256"

    @field_validator("JWT_SECRET")
    @classmethod
    def check_jwt_secret(cls, v: str) -> str:
        if not v:
            raise ValueError("JWT_SECRET must be set via environment variable")
        return v

    # Application
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = True


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
