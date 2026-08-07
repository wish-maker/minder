"""Ollama client manager for the model-management service.

Extracted from main.py into core/ per the service-structure standard (thin main +
core/, mirroring graph-rag/marketplace). Owns the Ollama client lifecycle and the
model list/pull/show/delete/test operations; main.py wires it into the FastAPI app
and injects it into routes/models_api.py.
"""

import logging
from typing import Any, Dict, List

from fastapi import HTTPException

from config import settings
from shared.ai.ollama_client_base import (  # noqa: F401 -- re-exported for main.py
    OLLAMA_AVAILABLE,
    OllamaClientBase,
)

logger = logging.getLogger("minder.model-management")

OLLAMA_HOST = settings.OLLAMA_HOST


class OllamaManager(OllamaClientBase):
    """Manage Ollama client connections for model lifecycle"""

    def __init__(self):
        super().__init__(host=OLLAMA_HOST)

    async def list_models(self) -> List[Dict[str, Any]]:
        """List all models from Ollama"""
        await self._ensure_initialized()

        assert self.client is not None
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

    async def pull_model(self, model_id: str) -> Dict[str, Any]:
        """Pull/download a model from Ollama library"""
        await self._ensure_initialized()

        try:
            logger.info(f"Pulling model: {model_id}")
            assert self.client is not None
            response = await self.client.pull(model=model_id, stream=False)
            return {"model": model_id, "status": "pulled", "details": response}
        except Exception as e:
            logger.error(f"❌ Failed to pull model {model_id}: {e}")
            raise HTTPException(
                status_code=503, detail=f"Failed to pull model: {str(e)}"
            )

    async def show_model(self, model_id: str) -> Dict[str, Any]:
        """Show detailed information about a model"""
        await self._ensure_initialized()

        assert self.client is not None
        try:
            response = await self.client.show(model=model_id)
            # show() returns a pydantic ShowResponse; normalise to a plain dict
            # to match the annotated return type and keep JSON serialisation stable.
            return response.model_dump()
        except Exception as e:
            logger.error(f"❌ Failed to show model {model_id}: {e}")
            raise HTTPException(status_code=404, detail=f"Model not found: {model_id}")

    async def delete_model(self, model_id: str) -> Dict[str, Any]:
        """Delete a model from local storage"""
        await self._ensure_initialized()

        try:
            logger.warning(f"Deleting model: {model_id}")
            assert self.client is not None
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
        await self._ensure_initialized()

        assert self.client is not None
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
