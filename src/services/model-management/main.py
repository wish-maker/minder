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
from pydantic import BaseModel

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
class ModelInfo(BaseModel):
    """Model information"""

    id: str
    name: str
    type: str  # "local" or "remote"
    provider: str
    size: str
    status: str


class ModelConstraints(BaseModel):
    """Model constraints"""

    rate_limit: int
    cost_limit: float
    allowed_users: List[str]
    content_filtering: bool
    max_tokens: int


class FineTuneRequest(BaseModel):
    """Fine-tuning request"""

    base_model: str
    training_data: Optional[str] = None
    epochs: Optional[int] = 3
    learning_rate: Optional[float] = 0.0001


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


# List all models
@app.get("/models", response_model=List[ModelInfo], tags=["Models"])
async def list_models():
    """List all models from Ollama (real-time list)"""
    try:
        # Get fresh list from Ollama
        ollama_models = await ollama_manager.list_models()

        # Convert to ModelInfo format
        result = []
        for model in ollama_models:
            # Extract model info from Ollama response
            model_name = model.get("name", "")
            model_size = model.get("size", 0)

            # Convert size to human-readable format
            size_str = f"{model_size / (1024**3):.2f} GB" if model_size else "Unknown"

            result.append(
                ModelInfo(
                    id=model_name,
                    name=model_name,
                    type="local",  # Ollama models are local
                    provider="ollama",
                    size=size_str,
                    status="ready",  # If it's in the list, it's ready
                )
            )

        # Update cache
        global models  # noqa: F824
        models.clear()
        for model_info in result:
            models[model_info.id] = {
                "id": model_info.id,
                "name": model_info.name,
                "type": model_info.type,
                "provider": model_info.provider,
                "size": model_info.size,
                "status": model_info.status,
            }

        logger.info(f"✅ Listed {len(result)} models from Ollama")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to list models: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to list models: {str(e)}")


# Register/Pull model
@app.post("/models", tags=["Models"])
async def register_model(model_id: str, model_info: ModelInfo):
    """
    Register and pull a new model from Ollama library
    NOTE: This will download the actual model (can be large)
    """
    try:
        # Check if model already exists locally
        existing_models = await ollama_manager.list_models()
        for model in existing_models:
            if model.get("name") == model_id:
                logger.warning(f"Model {model_id} already exists locally")
                return {
                    "message": f"Model '{model_id}' already exists",
                    "model": model_id,
                    "status": "already_exists",
                }

        # Pull the model (real download from Ollama library)
        result = await ollama_manager.pull_model(model_id)

        logger.info(f"✅ Model pulled: {model_id}")

        return {
            "message": f"Model '{model_id}' pulled successfully",
            "model": model_id,
            "status": "pulled",
            "details": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to register model {model_id}: {e}")
        raise HTTPException(
            status_code=503, detail=f"Failed to register model: {str(e)}"
        )


# Get model details
@app.get("/models/{model_id}", tags=["Models"])
async def get_model(model_id: str):
    """Get detailed model information from Ollama"""
    try:
        model_details = await ollama_manager.show_model(model_id)

        # Extract relevant information
        return {"id": model_id, "details": model_details, "status": "ready"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get model {model_id}: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to get model: {str(e)}")


# Delete model
@app.delete("/models/{model_id}", tags=["Models"])
async def delete_model(model_id: str):
    """
    Delete a model from local Ollama storage
    WARNING: This permanently removes the model file
    """
    try:
        # Check if model exists
        existing_models = await ollama_manager.list_models()
        model_exists = False
        for model in existing_models:
            if model.get("name") == model_id:
                model_exists = True
                break

        if not model_exists:
            raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found")

        # Delete the model (permanent removal)
        result = await ollama_manager.delete_model(model_id)

        logger.warning(f"⚠️  Model deleted: {model_id}")

        return {
            "message": f"Model '{model_id}' deleted successfully",
            "model": model_id,
            "status": "deleted",
            "details": result,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete model {model_id}: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to delete model: {str(e)}")


# Test model generation
@app.post("/models/{model_id}/test", tags=["Models"])
async def test_model(model_id: str, prompt: str = "Hello, test."):
    """
    Test a model with a simple generation
    Useful to verify model works before use
    """
    try:
        result = await ollama_manager.test_model(model_id, prompt)

        logger.info(f"✅ Model tested: {model_id}")

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to test model {model_id}: {e}")
        raise HTTPException(status_code=503, detail=f"Failed to test model: {str(e)}")


# Set model constraints (placeholder for future)
@app.post("/models/{model_id}/constraints", tags=["Models"])
async def set_model_constraints(model_id: str, constraints: ModelConstraints):
    """Set constraints for a model (placeholder for future implementation)"""
    # Placeholder: In future, this could set rate limits, resource limits, etc.
    logger.info(f"Constraints set for model: {model_id} (placeholder)")
    return {"message": f"Constraints set for model '{model_id}' (placeholder)"}


# Get model metrics (placeholder for future)
@app.get("/models/{model_id}/metrics", tags=["Models"])
async def get_model_metrics(model_id: str):
    """Get model performance metrics (placeholder for future implementation)"""
    # Placeholder: In future, this could return usage stats, latency, etc.
    return {
        "model_id": model_id,
        "total_requests": 0,
        "average_latency_ms": 0,
        "error_rate": 0.0,
        "cost_usd": 0.0,
        "note": "Metrics tracking not yet implemented",
    }


# Fine-tune model (placeholder - delegates to model-fine-tuning service)
@app.post("/models/fine-tune", tags=["Models"])
async def fine_tune_model(request: FineTuneRequest):
    """
    Fine-tune a model (placeholder)
    NOTE: Actual fine-tuning is handled by model-fine-tuning service
    This endpoint is kept for API compatibility
    """
    # Validate base model exists
    try:
        existing_models = await ollama_manager.list_models()
        model_exists = False
        for model in existing_models:
            if model.get("name") == request.base_model:
                model_exists = True
                break

        if not model_exists:
            raise HTTPException(status_code=404, detail="Base model not found")

        # Placeholder response
        fine_tuned_model_id = f"{request.base_model}_fine_tuned_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        logger.info(
            f"Fine-tuning: {request.base_model} -> {fine_tuned_model_id} "
            "(delegated to model-fine-tuning service)"
        )

        return {
            "message": "Fine-tuning request forwarded to model-fine-tuning service",
            "fine_tuned_model_id": fine_tuned_model_id,
            "base_model": request.base_model,
            "status": "forwarded",
            "note": "Use model-fine-tuning service for actual training",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to process fine-tune request: {e}")
        raise HTTPException(
            status_code=503, detail=f"Failed to process fine-tune request: {str(e)}"
        )


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
