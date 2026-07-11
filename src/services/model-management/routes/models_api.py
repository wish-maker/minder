"""Model CRUD + test endpoints (Ollama-backed).

Built via a factory with the Ollama manager, the in-memory cache dict, and the logger
injected by ``main`` — same pattern as the other services' route modules.
"""

from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException
from models import FineTuneRequest, ModelConstraints, ModelInfo


def build_models_router(*, ollama_manager, models, logger) -> APIRouter:
    router = APIRouter(tags=["Models"])

    @router.get("/models", response_model=List[ModelInfo])
    async def list_models():
        """List all models from Ollama (real-time), refreshing the cache."""
        try:
            ollama_models = await ollama_manager.list_models()
            result = []
            for model in ollama_models:
                model_name = model.get("name", "")
                model_size = model.get("size", 0)
                size_str = (
                    f"{model_size / (1024**3):.2f} GB" if model_size else "Unknown"
                )
                result.append(
                    ModelInfo(
                        id=model_name,
                        name=model_name,
                        type="local",
                        provider="ollama",
                        size=size_str,
                        status="ready",
                    )
                )
            models.clear()
            for m in result:
                models[m.id] = m.model_dump()
            logger.info(f"✅ Listed {len(result)} models from Ollama")
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to list models: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to list models: {str(e)}"
            )

    @router.post("/models")
    async def register_model(model_id: str, model_info: ModelInfo):
        """Register and pull a model from the Ollama library (may download a lot)."""
        try:
            for model in await ollama_manager.list_models():
                if model.get("name") == model_id:
                    logger.warning(f"Model {model_id} already exists locally")
                    return {
                        "message": f"Model '{model_id}' already exists",
                        "model": model_id,
                        "status": "already_exists",
                    }
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

    @router.get("/models/{model_id}")
    async def get_model(model_id: str):
        """Get detailed model information from Ollama."""
        try:
            details = await ollama_manager.show_model(model_id)
            return {"id": model_id, "details": details, "status": "ready"}
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to get model {model_id}: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to get model: {str(e)}"
            )

    @router.delete("/models/{model_id}")
    async def delete_model(model_id: str):
        """Permanently delete a model from local Ollama storage."""
        try:
            exists = any(
                m.get("name") == model_id for m in await ollama_manager.list_models()
            )
            if not exists:
                raise HTTPException(
                    status_code=404, detail=f"Model '{model_id}' not found"
                )
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
            raise HTTPException(
                status_code=503, detail=f"Failed to delete model: {str(e)}"
            )

    @router.post("/models/{model_id}/test")
    async def test_model(model_id: str, prompt: str = "Hello, test."):
        """Quick test-prompt generation to verify a model works."""
        try:
            result = await ollama_manager.test_model(model_id, prompt)
            logger.info(f"✅ Model tested: {model_id}")
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to test model {model_id}: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to test model: {str(e)}"
            )

    @router.post("/models/{model_id}/constraints")
    async def set_model_constraints(model_id: str, constraints: ModelConstraints):
        """Set constraints for a model. **Placeholder** — not yet implemented."""
        logger.info(f"Constraints set for model: {model_id} (placeholder)")
        return {"message": f"Constraints set for model '{model_id}' (placeholder)"}

    @router.get("/models/{model_id}/metrics")
    async def get_model_metrics(model_id: str):
        """Model performance metrics. **Placeholder** — returns zeros."""
        return {
            "model_id": model_id,
            "total_requests": 0,
            "average_latency_ms": 0,
            "error_rate": 0.0,
            "cost_usd": 0.0,
            "note": "Metrics tracking not yet implemented",
        }

    @router.post("/models/fine-tune")
    async def fine_tune_model(request: FineTuneRequest):
        """Fine-tune request. **Placeholder** — training is not performed here."""
        try:
            exists = any(
                m.get("name") == request.base_model
                for m in await ollama_manager.list_models()
            )
            if not exists:
                raise HTTPException(status_code=404, detail="Base model not found")
            fine_tuned_id = (
                f"{request.base_model}_fine_tuned_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )
            logger.info(
                f"Fine-tune request (placeholder): {request.base_model} -> {fine_tuned_id}"
            )
            return {
                "message": "Fine-tuning is not implemented in this service",
                "fine_tuned_model_id": fine_tuned_id,
                "base_model": request.base_model,
                "status": "not_implemented",
                "note": "Placeholder endpoint kept for API compatibility",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to process fine-tune request: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to process fine-tune request: {str(e)}"
            )

    return router
