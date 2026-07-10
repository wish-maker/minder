"""
Minder Model Management Service
Manages base models, fine-tuning, and deployment
Real Ollama integration for model lifecycle
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

# Ollama client for real model management
try:
    from ollama import AsyncClient

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("ollama package not installed. Install with: pip install ollama")

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")

# Initialize FastAPI
app = FastAPI(
    title="Minder Model Management",
    description="Model management and fine-tuning service",
    version="1.0.0",
)


# ============================================================================
# Prometheus Metrics
# ============================================================================

http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds", "HTTP request latency", ["method", "endpoint"]
)

models_registered_total = Gauge(
    "models_registered_total", "Total number of registered models"
)


# Pydantic models
from models import FineTuneRequest, ModelConstraints, ModelInfo  # noqa: E402,F401

# ============================================================================
# Ollama Client Management
# ============================================================================


class OllamaManager:
    """Manage Ollama client connections for model lifecycle"""

    def __init__(self):
        self.client: Optional[AsyncClient] = None
        self._initialized = False

    async def initialize(self):
        """Initialize Ollama client"""
        if not OLLAMA_AVAILABLE:
            raise RuntimeError("Ollama package not installed")

        try:
            self.client = AsyncClient(host=OLLAMA_HOST)
            self._initialized = True
            logger.info(f"✅ Ollama client initialized: {OLLAMA_HOST}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize Ollama client: {e}")
            raise

    async def list_models(self) -> List[Dict[str, Any]]:
        """List all models from Ollama"""
        if not self._initialized:
            await self.initialize()

        try:
            response = await self.client.list()
            models = response.get("models", [])
            logger.debug(f"Retrieved {len(models)} models from Ollama")
            return models
        except Exception as e:
            logger.error(f"❌ Failed to list models: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to list models: {str(e)}"
            )

    async def pull_model(self, model_id: str, stream: bool = False) -> Dict[str, Any]:
        """Pull/download a model from Ollama library"""
        if not self._initialized:
            await self.initialize()

        try:
            logger.info(f"Pulling model: {model_id}")
            response = await self.client.pull(model=model_id, stream=stream)
            return {"model": model_id, "status": "pulled", "details": response}
        except Exception as e:
            logger.error(f"❌ Failed to pull model {model_id}: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to pull model: {str(e)}"
            )

    async def show_model(self, model_id: str) -> Dict[str, Any]:
        """Show detailed information about a model"""
        if not self._initialized:
            await self.initialize()

        try:
            response = await self.client.show(model=model_id)
            return response
        except Exception as e:
            logger.error(f"❌ Failed to show model {model_id}: {e}")
            raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")

    async def delete_model(self, model_id: str) -> Dict[str, Any]:
        """Delete a model from local storage"""
        if not self._initialized:
            await self.initialize()

        try:
            logger.warning(f"Deleting model: {model_id}")
            response = await self.client.delete(model=model_id)
            return {"model": model_id, "status": "deleted", "details": response}
        except Exception as e:
            logger.error(f"❌ Failed to delete model {model_id}: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to delete model: {str(e)}"
            )

    async def test_model(
        self, model_id: str, prompt: str = "Hello, test."
    ) -> Dict[str, Any]:
        """Test a model with a simple generation"""
        if not self._initialized:
            await self.initialize()

        try:
            response = await self.client.generate(model=model_id, prompt=prompt)
            return {
                "model": model_id,
                "prompt": prompt,
                "response": response.get("response", ""),
                "status": "success",
            }
        except Exception as e:
            logger.error(f"❌ Failed to test model {model_id}: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to test model: {str(e)}"
            )


# Global Ollama manager
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
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": app.version,
        "models_registered": len(models),
    }


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Request tracking middleware
@app.middleware("http")
async def track_requests(request, call_next):
    """Track HTTP requests for metrics"""
    import time

    start_time = time.time()
    endpoint = request.url.path
    method = request.method

    response = await call_next(request)

    # Update metrics
    duration = time.time() - start_time
    http_requests_total.labels(
        method=method, endpoint=endpoint, status=response.status_code
    ).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
        duration
    )

    # Update models count
    if endpoint == "/health":
        models_registered_total.set(len(models))

    return response


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


@app.on_event("startup")
async def startup_event():
    """Initialize Ollama client on startup"""
    try:
        if not OLLAMA_AVAILABLE:
            logger.error("❌ Ollama package not available - service will not function")
            return

        await ollama_manager.initialize()

        # Test connection by listing models
        models = await ollama_manager.list_models()
        logger.info(f"✅ Connected to Ollama - {len(models)} models available")

    except Exception as e:
        logger.error(f"❌ Failed to initialize model-management service: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Model Management service shutting down...")
    # Ollama client doesn't need explicit cleanup


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
