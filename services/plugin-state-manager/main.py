# services/plugin-state-manager/main.py
"""
Plugin State Manager Service
Central plugin management, state control, and AI tools execution
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings
from routes import licensing, state, tools

from core.database import close_db_pool, get_db_pool, initialize_database

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
    print(f"🚀 {settings.APP_NAME} v{settings.VERSION} starting...")
    print(f"   Environment: {settings.ENVIRONMENT}")
    print(f"   Database: {settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}")

    # Initialize database pool
    await get_db_pool()

    # Initialize database schema
    await initialize_database()

    # Load default plugins
    from core.default_plugins import bootstrap_default_plugins

    await bootstrap_default_plugins()

    print(f"✅ {settings.APP_NAME} started successfully")

    yield

    # Shutdown
    print(f"🛑 Shutting down {settings.APP_NAME}...")
    await close_db_pool()
    print(f"✅ {settings.APP_NAME} stopped")


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
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "status": "healthy",
        "database": "connected" if pool else "disconnected",
    }


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
