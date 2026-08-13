"""Model CRUD + test endpoints (Ollama-backed).

Built via a factory with the Ollama manager, the in-memory cache dict, and the logger
injected by ``main`` — same pattern as the other services' route modules.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from models import (
    FineTuneRequest,
    ModelConstraints,
    ModelInfo,
    ModelPullRequest,
    ModelTestRequest,
)

from shared.auth.jwt_middleware import get_current_user_or_service
from shared.errors import backend_http_error
from shared.models import PaginatedList


def build_models_router(*, ollama_manager, models, logger) -> APIRouter:
    router = APIRouter(tags=["Models"])

    @router.get("/v1/models", response_model=PaginatedList[ModelInfo])
    @router.get(
        "/models",
        response_model=PaginatedList[ModelInfo],
        include_in_schema=False,
    )  # deprecated unversioned alias
    async def list_models(
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
    ):
        """List all models from Ollama (real-time), refreshing the cache.

        Returns the shared `{items, total, limit, offset}` envelope (#519, matching
        rag-pipeline's #501 conversion) so a caller can page and see the true total.
        Served at both /v1/models and the legacy /models directly — the old /models
        used a 301 redirect, which drops the method/body on non-GET clients (#147).
        """
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
            # Full list is in memory; slice + wrap in the shared envelope (#519).
            return PaginatedList.paginate(result, limit, offset)
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to list models: {e}")
            raise backend_http_error(e, "Listing models")

    @router.post("/v1/models", status_code=201)
    @router.post(
        "/models", status_code=201, include_in_schema=False
    )  # deprecated unversioned alias
    async def register_model(
        request: ModelPullRequest,
        response: Response,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Pull a model from the Ollama library (may download a lot).

        Body is just ``{"model_id": "..."}`` — the old design also demanded an ignored
        ModelInfo body and a query param (#145). Returns 201 on a fresh pull, 200 when
        the model already exists locally.

        Served at both /v1/models and the legacy /models directly — the old /models
        used a 301 redirect, which drops the method/body on non-GET clients (#147).
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
            raise backend_http_error(e, "Model registration")

    @router.get("/v1/models/{model_id}")
    @router.get(
        "/models/{model_id}", include_in_schema=False
    )  # deprecated unversioned alias
    async def get_model(model_id: str):
        """Get detailed model information from Ollama.

        Served at both /v1/models/{model_id} and the legacy /models/{model_id}
        directly — the old path used a 301 redirect, which drops the method/body on
        non-GET clients (#147).
        """
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
            # Promoted out of `details` (#328): "does this model support real
            # tool-calling" was previously only inferable from behavior -- a
            # live audit found a model answering fluently without ever
            # invoking a real tool, with nothing to check beforehand. Ollama's
            # own ShowResponse.capabilities (e.g. ["completion", "tools", ...])
            # was already in `details` unfiltered, just not surfaced.
            return {
                "id": model_id,
                "details": details,
                "capabilities": details.get("capabilities") or [],
                "status": "ready",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to get model {model_id}: {e}")
            raise backend_http_error(e, "Fetching model details")

    @router.delete("/v1/models/{model_id}")
    @router.delete(
        "/models/{model_id}", include_in_schema=False
    )  # deprecated unversioned alias
    async def delete_model(
        model_id: str,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Permanently delete a model from local Ollama storage.

        Served at both /v1/models/{model_id} and the legacy /models/{model_id}
        directly — the old path used a 301 redirect, which drops the method/body on
        non-GET clients (#147).
        """
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
            raise backend_http_error(e, "Model deletion")

    @router.post("/v1/models/{model_id}/test")
    @router.post(
        "/models/{model_id}/test", include_in_schema=False
    )  # deprecated unversioned alias
    async def test_model(model_id: str, request: ModelTestRequest):
        """Quick test-prompt generation to verify a model works.

        Prompt is a JSON body (``{"prompt": "..."}``) rather than a query string (#145).

        Served at both /v1/models/{model_id}/test and the legacy path directly — the
        old path used a 301 redirect, which drops the method/body on non-GET clients
        (#147).
        """
        try:
            # 404 for an unknown model instead of letting ollama's own 404 become
            # a blanket 503 that leaks the raw message (#532) — mirrors get_model
            # / delete_model (#145).
            exists = any(
                m.get("model") == model_id for m in await ollama_manager.list_models()
            )
            if not exists:
                raise HTTPException(
                    status_code=404, detail=f"Model '{model_id}' not found"
                )
            result = await ollama_manager.test_model(model_id, request.prompt)
            logger.info(f"✅ Model tested: {model_id}")
            return result
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"❌ Failed to test model {model_id}: {e}")
            raise backend_http_error(e, "Model test")

    @router.post("/v1/models/{model_id}/constraints")
    @router.post(
        "/models/{model_id}/constraints", include_in_schema=False
    )  # deprecated unversioned alias
    async def set_model_constraints(model_id: str, constraints: ModelConstraints):
        """Set constraints for a model. **Not implemented** — returns 501 (#145).

        The ModelConstraints body is kept so /docs documents the intended shape.

        Served at both /v1/models/{model_id}/constraints and the legacy path
        directly — the old path used a 301 redirect, which drops the method/body on
        non-GET clients (#147).
        """
        raise HTTPException(
            status_code=501,
            detail="Model constraints are not implemented in this service",
        )

    @router.get("/v1/models/{model_id}/metrics")
    @router.get(
        "/models/{model_id}/metrics", include_in_schema=False
    )  # deprecated unversioned alias
    async def get_model_metrics(model_id: str):
        """Model performance metrics. **Not implemented** — returns 501 (#145).

        Previously returned a 200 body of zeros, which read as real data in /docs.

        Served at both /v1/models/{model_id}/metrics and the legacy path directly —
        the old path used a 301 redirect, which drops the method/body on non-GET
        clients (#147).
        """
        raise HTTPException(
            status_code=501,
            detail="Metrics tracking is not implemented in this service",
        )

    @router.post("/v1/models/fine-tune")
    @router.post(
        "/models/fine-tune", include_in_schema=False
    )  # deprecated unversioned alias
    async def fine_tune_model(
        request: FineTuneRequest,
        current_user: dict = Depends(get_current_user_or_service),
    ):
        """Fine-tune request. **Not implemented** — returns 501 (#145).

        The FineTuneRequest body is kept so /docs documents the intended shape.

        Served at both /v1/models/fine-tune and the legacy /models/fine-tune
        directly — the old path used a 301 redirect, which drops the method/body on
        non-GET clients (#147).
        """
        raise HTTPException(
            status_code=501,
            detail="Fine-tuning is not implemented in this service",
        )

    return router
