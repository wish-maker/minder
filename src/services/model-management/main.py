"""
Minder Model Management Service
Manages base models, fine-tuning, and deployment
Real Ollama integration for model lifecycle
"""

import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI
from prometheus_client import Gauge

from config import settings

# Shared library (needs src/ on the path)
sys.path.insert(0, "/app/src")
# Domain logic lives in core/ (service-structure standard: thin main + core/).
from core.ollama_manager import (  # noqa: E402
    OLLAMA_AVAILABLE,
    OLLAMA_HOST,
    OllamaManager,
)

from shared.metrics import setup_metrics  # noqa: E402

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL))
logger = logging.getLogger("minder.model-management")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the Ollama client on startup; no explicit shutdown cleanup."""
    try:
        if not OLLAMA_AVAILABLE:
            logger.error("❌ Ollama package not available - service will not function")
        else:
            await ollama_manager.initialize()
            # Test connection by listing models
            models = await ollama_manager.list_models()
            logger.info(f"✅ Connected to Ollama - {len(models)} models available")
    except Exception as e:
        logger.error(f"❌ Failed to initialize model-management service: {e}")

    yield

    logger.info("Model Management service shutting down...")
    # Ollama client doesn't need explicit cleanup


app = FastAPI(
    title="Minder Model Management",
    description="Model management and fine-tuning service",
    version="1.0.0",
    lifespan=lifespan,
)

# Prometheus metrics: request-tracking middleware + /metrics endpoint
setup_metrics(app)


# ============================================================================
# Prometheus Metrics (domain-specific; HTTP request metrics from shared.metrics)
# ============================================================================

models_registered_total = Gauge(
    "models_registered_total", "Total number of registered models"
)


# Pydantic models
from models import FineTuneRequest, ModelConstraints, ModelInfo  # noqa: E402,F401

# Ollama client manager — domain logic lives in core/ollama_manager.py.
ollama_manager = OllamaManager()


# ============================================================================
# In-memory model storage (use PostgreSQL in production)
# ============================================================================
# NOTE: This is now just a cache. Ollama is the source of truth.
models: Dict[str, Dict[str, Any]] = {}

# Model CRUD/test endpoints live in routes/models_api.py (deps injected).
from routes.models_api import build_models_router  # noqa: E402

app.include_router(
    build_models_router(ollama_manager=ollama_manager, models=models, logger=logger)
)


# Health check
@app.get("/health", tags=["Health"])
async def health_check():
    """Service health check"""
    models_registered_total.set(len(models))
    return {
        "service": "model-management",
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "environment": settings.ENVIRONMENT,
        "models_registered": len(models),
    }


# Root endpoint
@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "name": "Minder Model Management",
        "version": app.version,
        "status": "operational",
        "ollama_available": OLLAMA_AVAILABLE,
        "ollama_host": OLLAMA_HOST if OLLAMA_AVAILABLE else None,
    }


# ============================================================================
# Startup/Shutdown Events
# ============================================================================


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
