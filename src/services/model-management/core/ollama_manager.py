"""Ollama client manager for the model-management service.

Extracted from main.py into core/ per the service-structure standard (thin main +
core/, mirroring graph-rag/marketplace). Owns the Ollama client lifecycle and the
model list/pull/show/delete/test operations; main.py wires it into the FastAPI app
and injects it into routes/models_api.py.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from config import settings

# Ollama client for real model management. Guarded so the module imports even when
# the package is absent (e.g. lint/tests); OLLAMA_AVAILABLE gates real use.
try:
    from ollama import AsyncClient

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False
    logging.warning("ollama package not installed. Install with: pip install ollama")

logger = logging.getLogger("minder.model-management")

OLLAMA_HOST = settings.OLLAMA_HOST


class OllamaManager:
    """Manage Ollama client connections for model lifecycle"""

    def __init__(self):
        self.client: Optional["AsyncClient"] = None
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
