# services/marketplace/main.py
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone

# Add src to path for shared module imports (MUST be before other imports)
sys.path.insert(0, "/app/src")

from core.database import close_pool, get_pool  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from config import settings  # noqa: E402
from shared.health import DependencyCheck, evaluate_dependencies  # noqa: E402
from shared.log import setup_logging  # noqa: E402
from shared.metrics import setup_metrics  # noqa: E402
from shared.utils.cors import add_cors_from_string  # noqa: E402

logger = setup_logging("marketplace", level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("Starting Minder Marketplace service...")
    await get_pool()  # Initialize database pool
    logger.info("Database pool initialized")

    # Run database migrations (idempotent schema initialization)
    from migrations import run_migrations

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
add_cors_from_string(
    app, settings.CORS_ALLOWED_ORIGINS, default_origins=_DEV_CORS_ORIGINS
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint — 503 when Postgres (the core store) is unreachable."""

    async def _postgres():
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")

    status, code, checks = await evaluate_dependencies(
        [DependencyCheck("postgres", _postgres, critical=True)]
    )
    return JSONResponse(
        status_code=code,
        content={
            "service": "marketplace",
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "version": app.version,
            "environment": settings.ENVIRONMENT,
            "checks": checks,
        },
    )


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
    # Match the platform's default {"detail": ...} envelope — was the only service
    # emitting a custom {"error", "detail"} shape (#147/C3).
    return JSONResponse(
        status_code=500,
        content={
            "detail": (
                str(exc)
                if settings.ENVIRONMENT == "development"
                else "Internal server error"
            ),
        },
    )


from routes.ai_tools import router as ai_tools_router  # noqa: E402
from routes.graph_dependencies import router as graph_dependencies_router  # noqa: E402
from routes.installations import router as installations_router  # noqa: E402
from routes.licensing import router as licensing_router  # noqa: E402
from routes.management import router as management_router  # noqa: E402

# Include routers
from routes.marketplace import router as marketplace_router  # noqa: E402

app.include_router(marketplace_router)
app.include_router(management_router)
app.include_router(installations_router)
app.include_router(ai_tools_router)
app.include_router(licensing_router)
app.include_router(graph_dependencies_router)
