"""
Webhook route management (MVP).

Maps fixed webhook paths declared in plugin manifests to plugin names and
dispatches incoming webhook requests to the execution engine. Routes are fixed
paths from the manifest — there is NO dynamic code execution.
"""

from typing import Dict

from core.state import logger, plugin_manifests, plugins_db, webhook_routes
from fastapi import HTTPException, Request


async def register_plugin_webhook(plugin_name: str, manifest: Dict):
    """
    Register webhook route for plugin.

    Args:
        plugin_name: Plugin name
        manifest: Plugin manifest

    SECURITY: Webhook routes are fixed paths from manifest.
    NO dynamic code execution.
    """
    trigger = manifest.get("spec", {}).get("trigger", {})
    if trigger.get("type") != "webhook":
        return

    webhook_config = trigger.get("webhook", {})
    webhook_path = webhook_config.get("path")

    if not webhook_path:
        logger.warning(f"Plugin {plugin_name} has no webhook path")
        return

    # Store route mapping (prefix with /webhook/ for endpoint matching)
    full_webhook_path = f"/webhook{webhook_path}"
    webhook_routes[full_webhook_path] = plugin_name
    plugin_manifests[plugin_name] = manifest

    logger.info(f"Registered webhook route: {full_webhook_path} -> {plugin_name}")


async def handle_webhook_request(webhook_path: str, request: Request) -> Dict:
    """
    Handle incoming webhook request.

    Args:
        webhook_path: Webhook path
        request: FastAPI request

    Returns:
        Response from execution engine
    """
    # Find plugin for this webhook
    plugin_name = webhook_routes.get(webhook_path)

    if not plugin_name:
        raise HTTPException(
            status_code=404, detail=f"No webhook registered at {webhook_path}"
        )

    # Get manifest
    manifest = plugin_manifests.get(plugin_name)

    if not manifest:
        raise HTTPException(
            status_code=500, detail=f"Plugin {plugin_name} manifest not loaded"
        )

    # Get webhook data
    try:
        if request.headers.get("content-type", "").startswith("application/json"):
            webhook_data = await request.json()
        else:
            # Form data
            form_data = await request.form()
            webhook_data = dict(form_data)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse webhook data: {e}"
        )

    # Validate secret if configured
    webhook_config = manifest.get("spec", {}).get("trigger", {}).get("webhook", {})
    secret_ref = webhook_config.get("secretRef")

    if secret_ref:
        # TODO: Validate against secrets store
        pass

    # Execute using execution engine
    import sys

    sys.path.insert(0, "/app/services/plugin-registry")
    from core.execution_engine import get_execution_engine

    engine = get_execution_engine()

    result = await engine.execute_webhook_trigger(manifest, webhook_data)

    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("error"))

    return {
        "message": "Webhook processed successfully",
        "plugin": plugin_name,
        "result": result.get("result", {}),
    }


async def register_all_webhooks_on_startup():
    """
    Register all webhook routes on startup.

    Called during startup to restore webhook routes from database.
    Ensures restart-safety.

    MVP: Loads from in-memory plugin_manifests populated by install endpoint.
    TODO: Load from PostgreSQL and restore all manifests.
    """
    # Clear existing routes
    webhook_routes.clear()

    # MVP: For now, just register webhooks from already-loaded manifests
    # In production, would load all manifests from PostgreSQL here
    for plugin_name, manifest in list(plugin_manifests.items()):
        await register_plugin_webhook(plugin_name, manifest)

    # TEMP: Load manifests from /tmp for testing (MVP restart-safety workaround)
    import glob

    import yaml

    manifest_files = glob.glob("/tmp/*-manifest.yml")
    logger.info(f"DEBUG: Found {len(manifest_files)} manifest files in /tmp")
    logger.info(
        f"DEBUG: plugins_db has {len(plugins_db)} plugins: {list(plugins_db.keys())}"
    )

    for manifest_file in manifest_files:
        try:
            logger.info(f"DEBUG: Loading manifest from {manifest_file}")
            with open(manifest_file, "r") as f:
                manifest = yaml.safe_load(f)
            plugin_name = manifest.get("metadata", {}).get("name")
            logger.info(
                f"DEBUG: Plugin name: {plugin_name}, in plugins_db: {plugin_name in plugins_db}"
            )
            if plugin_name and plugin_name in plugins_db:
                plugin_manifests[plugin_name] = manifest
                await register_plugin_webhook(plugin_name, manifest)
                logger.info(f"Loaded manifest from {manifest_file} for {plugin_name}")
        except Exception as e:
            logger.warning(f"Failed to load manifest from {manifest_file}: {e}")

    logger.info(f"Restored {len(webhook_routes)} webhook routes on startup")
