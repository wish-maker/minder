# services/marketplace/main.py
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.marketplace.config import settings
from services.marketplace.core.database import close_pool, get_pool

logger = logging.getLogger("minder.marketplace")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan"""
    # Startup
    logger.info("Starting Minder Marketplace service...")
    await get_pool()  # Initialize database pool
    logger.info("Database pool initialized")

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

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:8000",
        "http://localhost:8001",
        "http://localhost:8002",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "marketplace",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Minder Plugin Marketplace",
        "version": "1.0.0",
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
            "detail": str(exc) if settings.ENVIRONMENT == "development" else "An error occurred",
        },
    )


from services.marketplace.routes.ai_tools import router as ai_tools_router
from services.marketplace.routes.graph_dependencies import router as graph_dependencies_router
from services.marketplace.routes.licensing import router as licensing_router
from services.marketplace.routes.management import router as management_router

# Include routers
from services.marketplace.routes.marketplace import router as marketplace_router

app.include_router(marketplace_router)
app.include_router(management_router)
app.include_router(ai_tools_router)
app.include_router(licensing_router)
app.include_router(graph_dependencies_router)
