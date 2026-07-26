"""Model CRUD + test endpoints (Ollama-backed).

Built via a factory with the Ollama manager, the in-memory cache dict, and the logger
injected by ``main`` — same pattern as the other services' route modules.
"""

from typing import List

from fastapi import APIRouter, HTTPException, Response
from models import (
    FineTuneRequest,
    ModelConstraints,
    ModelInfo,
    ModelPullRequest,
    ModelTestRequest,
)


def build_models_router(*, ollama_manager, models, logger) -> APIRouter:
    router = APIRouter(tags=["Models"])

    @router.get("/models", response_model=List[ModelInfo])
    async def list_models():
        """List all models from Ollama (real-time), refreshing the cache."""
        try:
            ollama_models = await ollama_manager.list_models()
            result = []
            for model in ollama_models:
                # ollama>=0.5 renamed the list-entry field "name" -> "model"
                # (typed ListResponse.Model); .get("name") now silently yields "".
                model_name = model.get("model", "")
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

    @router.post("/models", status_code=201)
    async def register_model(request: ModelPullRequest, response: Response):
        """Pull a model from the Ollama library (may download a lot).

        Body is just ``{"model_id": "..."}`` — the old design also demanded an ignored
        ModelInfo body and a query param (#145). Returns 201 on a fresh pull, 200 when
        the model already exists locally.
        """
        model_id = request.model_id
        try:
            for model in await ollama_manager.list_models():
                if model.get("model") == model_id:
                    logger.warning(f"Model {model_id} already exists locally")
                    response.status_code = 200
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
            exists = any(
                m.get("model") == model_id for m in await ollama_manager.list_models()
            )
            if not exists:
                # 404 for an unknown model instead of the old blanket 503 — distinguish
                # "not found" from a real Ollama outage (#145). delete_model already
                # did this; get_model now matches.
                raise HTTPException(
                    status_code=404, detail=f"Model '{model_id}' not found"
                )
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
                m.get("model") == model_id for m in await ollama_manager.list_models()
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
    async def test_model(model_id: str, request: ModelTestRequest):
        """Quick test-prompt generation to verify a model works.

        Prompt is a JSON body (``{"prompt": "..."}``) rather than a query string (#145).
        """
        try:
            result = await ollama_manager.test_model(model_id, request.prompt)
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
        """Set constraints for a model. **Not implemented** — returns 501 (#145).

        The ModelConstraints body is kept so /docs documents the intended shape.
        """
        raise HTTPException(
            status_code=501,
            detail="Model constraints are not implemented in this service",
        )

    @router.get("/models/{model_id}/metrics")
    async def get_model_metrics(model_id: str):
        """Model performance metrics. **Not implemented** — returns 501 (#145).

        Previously returned a 200 body of zeros, which read as real data in /docs.
        """
        raise HTTPException(
            status_code=501,
            detail="Metrics tracking is not implemented in this service",
        )

    @router.post("/models/fine-tune")
    async def fine_tune_model(request: FineTuneRequest):
        """Fine-tune request. **Not implemented** — returns 501 (#145).

        The FineTuneRequest body is kept so /docs documents the intended shape.
        """
        raise HTTPException(
            status_code=501,
            detail="Fine-tuning is not implemented in this service",
        )

    return router
