"""
Marketplace AI-tool synchronization.

When a plugin is loaded, its AI tools are pushed to the marketplace service so they
show up in the tool catalog. Tools come from either a manifest's ``ai_tools`` (manifest
plugins) or a module plugin's in-code ``AI_TOOLS`` class attribute (passed in by the
loader). This module owns the HTTP helpers that talk to the marketplace API.
"""

import asyncio
import os
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from core.state import logger

# Trusted internal token for service-to-service marketplace writes (this sync runs at
# startup with no user JWT). Sent as X-Service-Token; the marketplace accepts it via
# get_current_user_or_service. Empty -> no header (marketplace will require a user JWT).
SERVICE_SYNC_TOKEN = os.environ.get("SERVICE_SYNC_TOKEN", "")

# One resolved marketplace base URL for the whole module — the two call sites used to
# each `os.environ.get("MARKETPLACE_URL", ...)` with DIFFERENT defaults ("marketplace"
# vs "minder-marketplace"), so if the env were unset the /ai/sync call would hit a
# non-resolving host. Single source, correct container name.
MARKETPLACE_URL = os.environ.get("MARKETPLACE_URL", "http://minder-marketplace:8002")


def _service_headers() -> Dict[str, str]:
    return {"X-Service-Token": SERVICE_SYNC_TOKEN} if SERVICE_SYNC_TOKEN else {}


# The registry syncs plugins at startup; during a co-restart the marketplace may not
# be resolvable/ready yet, and this sync had no retry — the plugin was silently
# skipped until the next registry restart (#230). Retry connection/DNS failures a few
# times so the catalog populates on the first boot.
_MKT_RETRIES = 4
_MKT_RETRY_DELAY = 2.0  # seconds between marketplace connection retries


async def _mkt_request(method: str, url: str, **kwargs) -> httpx.Response:
    """Make a marketplace HTTP call, retrying briefly on connection/DNS errors."""
    last_error: Optional[Exception] = None
    for attempt in range(1, _MKT_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                return await client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last_error = exc
            logger.info(
                f"Marketplace not ready ({type(exc).__name__}), "
                f"retry {attempt}/{_MKT_RETRIES}"
            )
            await asyncio.sleep(_MKT_RETRY_DELAY)
    raise last_error if last_error else RuntimeError("marketplace request failed")


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
    description: Optional[str] = None,
    author: Optional[str] = None,
):
    """
    Automatically sync AI tools from plugin manifest to marketplace

    This function is called when a plugin is loaded to automatically
    register its AI tools in the marketplace database.

    Args:
        plugin_name: Name of the plugin
        plugin_dir: Path to plugin directory
        module_ai_tools: in-code AI_TOOLS for module plugins (no manifest.yml)
        description: the plugin's real description (module plugins only --
            manifest plugins carry their own via manifest.yml). Found live:
            every module plugin synced to the marketplace with an empty
            description because this was never threaded through, even though
            the caller (plugin_loader.py) already has it from PluginMetadata.
        author: same gap, for the plugin's real author.
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
        # dict to describe the plugin (synthesised for module plugins, using the
        # caller's real description/author instead of a blank placeholder).
        if manifest is None:
            manifest = {
                "name": plugin_name,
                "version": "1.0.0",
                "description": description or "",
            }
            if author:
                manifest["author"] = author
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
        response = await _mkt_request(
            "POST",
            f"{MARKETPLACE_URL}/v1/marketplace/ai/sync",
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


async def _reconcile_marketplace_plugin(
    plugin_id: str, plugin_name: str, display_name: str, description: str, author: str
) -> None:
    """Push the plugin's current display_name/description/author onto an
    already-existing marketplace row.

    Found live: 4 first-party plugins were created under the old sync code
    (before description/author were threaded through at all) and stayed
    stuck with empty description / author "Unknown" forever, since
    get_or_create_marketplace_plugin's "found existing" branch returned the
    id without ever writing the caller's (correct) metadata back (#402
    point 4). Best-effort -- a failed PUT here shouldn't block the AI-tool
    sync that follows, so log and move on rather than raising.
    """
    try:
        response = await _mkt_request(
            "PUT",
            f"{MARKETPLACE_URL}/v1/marketplace/plugins/{plugin_id}",
            json={
                "display_name": display_name,
                "description": description,
                "author": author,
            },
            headers=_service_headers(),
        )
        if response.status_code != 200:
            logger.warning(
                f"Failed to reconcile marketplace metadata for {plugin_name}: "
                f"{response.status_code}"
            )
    except Exception as e:
        logger.warning(f"Error reconciling marketplace metadata for {plugin_name}: {e}")


async def get_or_create_marketplace_plugin(
    plugin_name: str, manifest: dict
) -> Optional[str]:
    """
    Get existing plugin ID from marketplace or create a new entry

    Args:
        plugin_name: Name of the plugin
        manifest: Plugin manifest dictionary

    Returns:
        Plugin UUID or None if failed
    """
    try:
        # Create display_name from description (first sentence, max 200 chars) --
        # but ONLY when that's genuinely shorter than the full description. Every
        # first-party plugin's description today is exactly one sentence (found
        # live: Available Plugins cards showed the same sentence twice, once as
        # the card title and once as the body, because splitting a one-sentence
        # description on "." just returns that whole sentence back). Falling back
        # to the plugin's own name keeps a real, distinct title in that case.
        # Computed once so both the found-existing and create branches use the
        # same current metadata instead of only the create path ever seeing it.
        description = manifest.get("description", plugin_name)
        _sentences = [s.strip() for s in description.split(".") if s.strip()]
        if len(_sentences) > 1:
            display_name = _sentences[0][:200]
        else:
            display_name = plugin_name.replace("_", " ").replace("-", " ").title()
        author = manifest.get("author", "Unknown")

        # Search for an existing plugin by name
        search_response = await _mkt_request(
            "GET",
            f"{MARKETPLACE_URL}/v1/marketplace/plugins/search",
            params={"q": plugin_name},
        )

        if search_response.status_code == 200:
            results = search_response.json()
            plugins = results.get("plugins", [])

            # Check if plugin with matching name exists
            for plugin in plugins:
                if plugin.get("name") == plugin_name:
                    logger.debug(f"Found existing marketplace plugin: {plugin_name}")
                    plugin_id = plugin.get("id")
                    await _reconcile_marketplace_plugin(
                        plugin_id, plugin_name, display_name, description, author
                    )
                    return plugin_id

        # Plugin doesn't exist, create it
        logger.info(f"Creating marketplace entry for plugin: {plugin_name}")

        # Build plugin data - only include repository_url if it's a valid URL
        plugin_data = {
            "name": plugin_name,
            "display_name": display_name,
            "description": description,
            "author": author,
            "pricing_model": "free",
            "base_tier": "community",
            "status": "approved",
        }

        # Only include repository_url if it exists and is not empty
        repository = manifest.get("repository")
        if repository and repository.strip():
            plugin_data["repository_url"] = repository

        create_response = await _mkt_request(
            "POST",
            f"{MARKETPLACE_URL}/v1/marketplace/plugins",
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
