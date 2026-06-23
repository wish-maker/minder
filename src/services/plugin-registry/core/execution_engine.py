"""
MVP Execution Engine

Processes trigger → action pipeline.
NO code execution - only template substitution and fixed action handlers.
"""

import logging
import os
import re
import uuid
from typing import Dict, Any, Optional
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

# Ollama URL from environment or default to local
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://minder-ollama:11434")


class TemplateEngine:
    """
    Simple template engine for extracting values from input data.

    Template syntax: {{ .field.name }} or {{ .field }}

    SECURITY: NO eval(), NO exec(), NO code execution.
    Only field extraction from input data.
    """

    # Pattern to match {{ .field.name }} or {{ .field }}
    # The dot is REQUIRED (prevents code injection)
    TEMPLATE_PATTERN = re.compile(r"\{\{\s*\.([a-zA-Z0-9_.]+)\s*\}\}")

    @staticmethod
    def render(template: str, context: Dict[str, Any]) -> str:
        """
        Render template with context data.

        Args:
            template: Template string with {{ .field }} placeholders
            context: Input data (usually webhook payload)

        Returns:
            Rendered string with placeholders replaced

        Raises:
            ValueError: If template references missing field
        """

        def replace_match(match):
            field_path = match.group(1)
            value = TemplateEngine._get_nested_value(context, field_path)

            if value is None:
                raise ValueError(f"Template references missing field: .{field_path}")

            return str(value)

        result = TemplateEngine.TEMPLATE_PATTERN.sub(replace_match, template)
        return result

    @staticmethod
    def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
        """
        Get nested value from dict using dot notation.

        Args:
            data: Source dictionary
            path: Dot-separated path (e.g., "author.username")

        Returns:
            Value at path, or None if not found
        """
        keys = path.split(".")
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    return None
            else:
                return None

        return value

    @staticmethod
    def render_dict(
        template_dict: Dict[str, str], context: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Render all string values in a dictionary.

        Args:
            template_dict: Dictionary with template values
            context: Input data

        Returns:
            Dictionary with templates rendered
        """
        result = {}
        for key, value in template_dict.items():
            if isinstance(value, str):
                result[key] = TemplateEngine.render(value, context)
            elif isinstance(value, dict):
                result[key] = TemplateEngine.render_dict(value, context)
            else:
                result[key] = value
        return result


class ExecutionEngine:
    """
    Executes plugin pipelines: trigger → action

    For MVP: webhook trigger → store-vector action
    """

    def __init__(
        self, qdrant_url: str = "http://minder-qdrant:6333", ollama_url: str = None
    ):
        """
        Initialize execution engine.

        Args:
            qdrant_url: Qdrant server URL
            ollama_url: Ollama server URL (defaults to OLLAMA_BASE_URL env or local)
        """
        self.qdrant_url = qdrant_url
        self.ollama_url = ollama_url or OLLAMA_BASE_URL
        self.template_engine = TemplateEngine()
        self.http_client = None  # Created on first use

        # Action handlers registry (fixed functions, NO dynamic imports)
        self._action_handlers = {"store-vector": self._handle_store_vector}

    async def _get_http_client(self):
        """Get or create HTTP client"""
        if self.http_client is None:
            self.http_client = httpx.AsyncClient(timeout=30.0)
        return self.http_client

    async def close(self):
        """Close HTTP client"""
        if self.http_client:
            await self.http_client.aclose()
            self.http_client = None

    async def execute_webhook_trigger(
        self, manifest: Dict, webhook_data: Dict
    ) -> Dict[str, Any]:
        """
        Execute webhook trigger pipeline.

        Args:
            manifest: Plugin manifest
            webhook_data: Incoming webhook payload

        Returns:
            Execution result with status and output

        SECURITY: All action handlers are fixed functions.
        Manifest only supplies parameters.
        """
        plugin_name = manifest.get("metadata", {}).get("name", "unknown")
        spec = manifest.get("spec", {})

        try:
            # Extract trigger config
            trigger = spec.get("trigger", {})
            webhook_config = trigger.get("webhook", {})

            # Validate secret if present
            secret_ref = webhook_config.get("secretRef")
            if secret_ref:
                # TODO: Validate against secrets store
                logger.debug(f"Would validate secret: {secret_ref}")

            # Execute action
            action = spec.get("action", {})
            action_type = action.get("type")

            if action_type not in self._action_handlers:
                raise ValueError(f"Unknown action type: {action_type}")

            handler = self._action_handlers[action_type]
            result = await handler(manifest, webhook_data)

            return {
                "status": "success",
                "plugin": plugin_name,
                "action": action_type,
                "result": result,
            }

        except Exception as e:
            logger.error(f"Execution failed for {plugin_name}: {e}")
            return {"status": "error", "plugin": plugin_name, "error": str(e)}

    async def _handle_store_vector(
        self, manifest: Dict, input_data: Dict
    ) -> Dict[str, Any]:
        """
        Store text in Qdrant with embedding.

        FIXED FUNCTION - manifest only supplies parameters.
        NO code execution based on manifest content.

        Args:
            manifest: Plugin manifest with store config
            input_data: Input data (webhook payload)

        Returns:
            Result with point ID and vector count
        """
        plugin_name = manifest.get("metadata", {}).get("name", "unknown")
        store_config = manifest.get("spec", {}).get("action", {}).get("store", {})

        # Extract parameters from manifest (NOT code)
        collection = store_config.get("collection")
        input_config = store_config.get("input", {})
        embed_model = store_config.get("embedModel", "all-minilm")

        # Render templates from input data
        text_template = input_config.get("text", "")
        text = self.template_engine.render(text_template, input_data)

        metadata_template = input_config.get("metadata", {})
        metadata = self.template_engine.render_dict(metadata_template, input_data)

        logger.info(
            f"Storing vector for {plugin_name}: collection={collection}, text_length={len(text)}"
        )

        # Validate text is not empty
        if not text or not text.strip():
            raise ValueError("Text template rendered to empty string")

        # Generate embedding using Ollama
        embedding = None
        try:
            client = await self._get_http_client()

            # Map common model names to actual Ollama model names
            model_map = {
                "all-minilm": "nomic-embed-text",
                "nomic-embed-text": "nomic-embed-text",
                "mxbai-embed-large": "nomic-embed-text",
            }
            ollama_model = model_map.get(embed_model, "nomic-embed-text")

            logger.info(f"Generating embedding with model: {ollama_model}")

            response = await client.post(
                f"{self.ollama_url}/api/embed",
                json={"model": ollama_model, "input": text},
            )

            if response.status_code != 200:
                raise ValueError(
                    f"Ollama embedding failed: {response.status_code} - {response.text}"
                )

            embed_data = response.json()
            embedding = embed_data.get("embeddings", [])[0]

            logger.info(f"Generated embedding: dim={len(embedding)}")

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

        # Ensure collection exists in Qdrant
        try:
            client = await self._get_http_client()

            # Check if collection exists
            collections_response = await client.get(
                f"{self.qdrant_url}/collections/{collection}"
            )

            if collections_response.status_code == 404:
                # Create collection
                logger.info(f"Creating Qdrant collection: {collection}")

                create_response = await client.put(
                    f"{self.qdrant_url}/collections/{collection}",
                    json={"vectors": {"size": len(embedding), "distance": "Cosine"}},
                )

                if create_response.status_code not in [200, 201]:
                    raise ValueError(
                        f"Failed to create collection: {create_response.text}"
                    )

                logger.info(f"Created collection: {collection}")

        except Exception as e:
            logger.error(f"Collection check/create failed: {e}")
            raise

        # Store vector in Qdrant
        point_id = str(uuid.uuid4())
        try:
            client = await self._get_http_client()

            # Prepare payload with metadata
            payload = {
                "text": text,
                "plugin": plugin_name,
                "timestamp": datetime.now().isoformat(),
            }
            payload.update(metadata)

            upsert_response = await client.put(
                f"{self.qdrant_url}/collections/{collection}/points",
                json={
                    "points": [
                        {"id": point_id, "vector": embedding, "payload": payload}
                    ]
                },
            )

            if upsert_response.status_code != 200:
                raise ValueError(
                    f"Qdrant upsert failed: {upsert_response.status_code} - {upsert_response.text}"
                )

            logger.info(f"Stored vector: point_id={point_id}, collection={collection}")

        except Exception as e:
            logger.error(f"Qdrant storage failed: {e}")
            raise

        return {
            "point_id": point_id,
            "collection": collection,
            "text_length": len(text),
            "metadata": metadata,
            "embedding_dim": len(embedding),
        }


# Singleton instance (created on startup)
_execution_engine: Optional[ExecutionEngine] = None


def get_execution_engine() -> ExecutionEngine:
    """Get or create execution engine singleton"""
    global _execution_engine
    if _execution_engine is None:
        _execution_engine = ExecutionEngine()
    return _execution_engine


def set_execution_engine(engine: ExecutionEngine):
    """Set execution engine singleton (for dependency injection)"""
    global _execution_engine
    _execution_engine = engine
