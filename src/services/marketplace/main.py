# services/marketplace/main.py
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime

# Add src to path for shared module imports (MUST be before other imports)
sys.path.insert(0, "/app/src")

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from services.marketplace.config import settings  # noqa: E402
from services.marketplace.core.database import close_pool, get_pool  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.marketplace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("Starting Minder Marketplace service...")
    await get_pool()  # Initialize database pool
    logger.info("Database pool initialized")

    # Run database migrations (idempotent schema initialization)
    from services.marketplace.migrations import run_migrations

    pool = await get_pool()
    await run_migrations(pool)
    logger.info("Database migrations completed")

    yield

    # Shutdown
    logger.info("Shutting down Minder Marketplace service...")
    await close_pool()
    logger.info("Database pool closed")


# Create FastAPI app
app = FastAPI(
    title="Minder Plugin Marketplace",
    description="Plugin marketplace and licensing system",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Add CORS middleware — origins from env (comma-separated CORS_ALLOWED_ORIGINS),
# falling back to the dev localhost list when it is unset.
_DEV_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://localhost:3002",
    "http://localhost:8000",
    "http://localhost:8001",
    "http://localhost:8002",
]
cors_origins = (
    settings.CORS_ALLOWED_ORIGINS.split(",")
    if settings.CORS_ALLOWED_ORIGINS
    else _DEV_CORS_ORIGINS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "service": "marketplace",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": settings.ENVIRONMENT,
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Minder Plugin Marketplace",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": (
                str(exc)
                if settings.ENVIRONMENT == "development"
                else "An error occurred"
            ),
        },
    )


from services.marketplace.routes.ai_tools import router as ai_tools_router  # noqa: E402
from services.marketplace.routes.graph_dependencies import (  # noqa: E402
    router as graph_dependencies_router,
)
from services.marketplace.routes.licensing import (  # noqa: E402
    router as licensing_router,
)
from services.marketplace.routes.management import (  # noqa: E402
    router as management_router,
)

# Include routers
from services.marketplace.routes.marketplace import (  # noqa: E402
    router as marketplace_router,
)

app.include_router(marketplace_router)
app.include_router(management_router)
app.include_router(ai_tools_router)
app.include_router(licensing_router)
app.include_router(graph_dependencies_router)
