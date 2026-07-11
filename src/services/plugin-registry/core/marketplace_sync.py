"""
Marketplace AI-tool synchronization.

When a plugin is loaded, its manifest's ``ai_tools`` are pushed to the marketplace
service so they show up in the tool catalog. This module owns the two HTTP helpers
that talk to the marketplace API; it is called by the plugin loader.
"""

import os
from pathlib import Path

import httpx
from core.state import logger


async def sync_plugin_ai_tools(plugin_name: str, plugin_dir: Path):
    """
    Automatically sync AI tools from plugin manifest to marketplace

    This function is called when a plugin is loaded to automatically
    register its AI tools in the marketplace database.

    Args:
        plugin_name: Name of the plugin
        plugin_dir: Path to plugin directory
    """
    try:
        # Load plugin manifest
        manifest_file = plugin_dir / "manifest.yml"
        if not manifest_file.exists():
            manifest_file = plugin_dir / "manifest.json"

        if not manifest_file.exists():
            logger.debug(f"No manifest found for plugin {plugin_name}")
            return

        # Load manifest
        import yaml

        with open(manifest_file, "r") as f:
            if manifest_file.suffix in [".yaml", ".yml"]:
                manifest = yaml.safe_load(f)
            else:
                import json

                manifest = json.load(f)

        # Check if plugin has AI tools
        if "ai_tools" not in manifest:
            logger.debug(f"No AI tools defined in manifest for {plugin_name}")
            return

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
                f"{marketplace_url}/v1/marketplace/plugins", json=plugin_data
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
