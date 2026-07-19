"""
Marketplace AI-tool synchronization.

When a plugin is loaded, its AI tools are pushed to the marketplace service so they
show up in the tool catalog. Tools come from either a manifest's ``ai_tools`` (manifest
plugins) or a module plugin's in-code ``AI_TOOLS`` class attribute (passed in by the
loader). This module owns the HTTP helpers that talk to the marketplace API.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from core.state import logger

# Trusted internal token for service-to-service marketplace writes (this sync runs at
# startup with no user JWT). Sent as X-Service-Token; the marketplace accepts it via
# get_current_user_or_service. Empty -> no header (marketplace will require a user JWT).
SERVICE_SYNC_TOKEN = os.environ.get("SERVICE_SYNC_TOKEN", "")


def _service_headers() -> Dict[str, str]:
    return {"X-Service-Token": SERVICE_SYNC_TOKEN} if SERVICE_SYNC_TOKEN else {}


def _to_marketplace_tool(tool: Dict) -> Dict:
    """Normalise a tool declaration to the shape the marketplace importer expects.

    The AI_TOOLS / manifest ai_tools schema uses an OpenAI/Ollama nested JSON Schema
    for ``parameters`` (``{type, properties, required}``) and an ``action``. The
    marketplace importer expects a FLAT ``parameters`` map (``{param: {type, ...,
    required: bool}}``) plus ``type``/``endpoint``/``method``. Convert between them so
    module-plugin tools populate the catalog. Already-flat tools pass through.
    """
    params = tool.get("parameters") or {}
    # Nested JSON Schema -> flat param map (the importer's expected shape).
    if isinstance(params, dict) and "properties" in params:
        required = set(params.get("required", []) or [])
        flat = {
            name: {
                **(spec if isinstance(spec, dict) else {}),
                "required": name in required,
            }
            for name, spec in (params.get("properties") or {}).items()
        }
    else:
        flat = params
    action = tool.get("action")
    out = {
        "name": tool.get("name"),
        "description": tool.get("description", ""),
        "parameters": flat,
        "type": tool.get("type", "action" if action else "analysis"),
        "method": tool.get("method", "POST"),
    }
    endpoint = tool.get("endpoint") or (f"/actions/{action}" if action else None)
    if endpoint:
        out["endpoint"] = endpoint
    return out


async def sync_plugin_ai_tools(
    plugin_name: str,
    plugin_dir: Path,
    module_ai_tools: Optional[List[Dict]] = None,
):
    """
    Automatically sync AI tools from plugin manifest to marketplace

    This function is called when a plugin is loaded to automatically
    register its AI tools in the marketplace database.

    Args:
        plugin_name: Name of the plugin
        plugin_dir: Path to plugin directory
    """
    try:
        # Load a plugin manifest if one exists (manifest plugins).
        manifest = None
        manifest_file = plugin_dir / "manifest.yml"
        if not manifest_file.exists():
            manifest_file = plugin_dir / "manifest.json"
        if manifest_file.exists():
            import yaml

            with open(manifest_file, "r") as f:
                if manifest_file.suffix in [".yaml", ".yml"]:
                    manifest = yaml.safe_load(f)
                else:
                    import json

                    manifest = json.load(f)

        # Tools come from the manifest (manifest plugins) or the passed-in module
        # AI_TOOLS (module plugins, which have no manifest).
        raw_tools = (manifest or {}).get("ai_tools") or module_ai_tools or []
        if not raw_tools:
            logger.debug(f"No AI tools to sync for {plugin_name}")
            return

        # Normalise to the marketplace importer's shape, and ensure we have a manifest
        # dict to describe the plugin (synthesised for module plugins).
        if manifest is None:
            manifest = {"name": plugin_name, "version": "1.0.0", "description": ""}
        manifest = {
            **manifest,
            "ai_tools": [_to_marketplace_tool(t) for t in raw_tools],
        }

        # Get or create plugin in marketplace
        plugin_id = await get_or_create_marketplace_plugin(plugin_name, manifest)

        if not plugin_id:
            logger.warning(
                f"Could not get/create marketplace plugin ID for {plugin_name}"
            )
            return

        # Call marketplace sync API
        marketplace_url = os.environ.get("MARKETPLACE_URL", "http://marketplace:8002")

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{marketplace_url}/v1/marketplace/ai/sync",
                json={
                    "plugin_name": plugin_name,
                    "plugin_id": plugin_id,
                    "manifest": manifest,
                },
                headers=_service_headers(),
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"✅ Synced {result.get('tools_imported', 0)} AI tools for {plugin_name}"
                )
            else:
                logger.warning(
                    f"Failed to sync AI tools for {plugin_name}: {response.status_code}"
                )

    except Exception as e:
        logger.error(f"Error syncing AI tools for {plugin_name}: {e}")


async def get_or_create_marketplace_plugin(plugin_name: str, manifest: dict) -> str:
    """
    Get existing plugin ID from marketplace or create a new entry

    Args:
        plugin_name: Name of the plugin
        manifest: Plugin manifest dictionary

    Returns:
        Plugin UUID or None if failed
    """
    try:
        marketplace_url = os.environ.get(
            "MARKETPLACE_URL", "http://minder-marketplace:8002"
        )

        # Try to find existing plugin by name
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Search for existing plugin
            search_response = await client.get(
                f"{marketplace_url}/v1/marketplace/plugins/search",
                params={"q": plugin_name},
            )

            if search_response.status_code == 200:
                results = search_response.json()
                plugins = results.get("plugins", [])

                # Check if plugin with matching name exists
                for plugin in plugins:
                    if plugin.get("name") == plugin_name:
                        logger.debug(
                            f"Found existing marketplace plugin: {plugin_name}"
                        )
                        return plugin.get("id")

            # Plugin doesn't exist, create it
            logger.info(f"Creating marketplace entry for plugin: {plugin_name}")

            # Create display_name from description (first sentence, max 200 chars)
            description = manifest.get("description", plugin_name)
            display_name = (
                description.split(".")[0][:200] if description else plugin_name
            )

            # Build plugin data - only include repository_url if it's a valid URL
            plugin_data = {
                "name": plugin_name,
                "display_name": display_name,
                "description": description,
                "author": manifest.get("author", "Unknown"),
                "pricing_model": "free",
                "base_tier": "community",
                "status": "approved",
            }

            # Only include repository_url if it exists and is not empty
            repository = manifest.get("repository")
            if repository and repository.strip():
                plugin_data["repository_url"] = repository

            create_response = await client.post(
                f"{marketplace_url}/v1/marketplace/plugins",
                json=plugin_data,
                headers=_service_headers(),
            )

            if create_response.status_code in [200, 201]:
                plugin_data = create_response.json()
                logger.info(
                    f"Created marketplace plugin entry: {plugin_name} -> {plugin_data.get('id')}"
                )
                return plugin_data.get("id")
            else:
                logger.warning(
                    f"Failed to create marketplace plugin: {create_response.status_code}"
                )
                logger.warning(f"Response: {create_response.text}")
                return None

    except Exception as e:
        logger.error(f"Error getting/creating marketplace plugin: {e}")
        return None
