"""
Minder API Gateway & Plugin Registry (Merged Service)
This service combines the functionality of both API Gateway and Plugin Registry
to reduce network latency and simplify deployment.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from config import get_settings
from routes import ai, plugins, health

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan events for startup and shutdown
    """
    # Startup
    logger.info(f"Starting {settings.api_title} v{settings.api_version}")
    logger.info(f"Environment: {settings.environment}")

    # Initialize any resources here
    # - Database connections
    # - Redis connections
    # - Load plugins into memory
    # - Initialize caches

    logger.info("Service initialized successfully")

    yield

    # Shutdown
    logger.info("Shutting down service...")
    # Clean up resources
    logger.info("Service stopped")


# Create FastAPI app
app = FastAPI(
    title=settings.api_title,
    version=settings.api_version,
    description="Merged API Gateway and Plugin Registry service",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers from both services
# API Gateway routes
app.include_router(
    ai.router,
    prefix="/api",
    tags=["AI"]
)

# Plugin Registry routes
app.include_router(
    plugins.router,
    prefix=settings.plugin_registry_path,
    tags=["Plugins"]
)

# Health check routes
app.include_router(
    health.router,
    tags=["Health"]
)


@app.get("/")
async def root():
    """
    Root endpoint - service information
    """
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "environment": settings.environment,
        "endpoints": {
            "api": "/api/*",
            "plugins": settings.plugin_registry_path + "/*",
            "health": "/health",
            "docs": "/docs"
        },
        "merged_services": [
            "API Gateway",
            "Plugin Registry"
        ]
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.environment == "development",
        log_level="info"
    )
