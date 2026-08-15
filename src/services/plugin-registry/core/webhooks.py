"""
Webhook route management (MVP).

Maps fixed webhook paths declared in plugin manifests to plugin names and
dispatches incoming webhook requests to the execution engine. Routes are fixed
paths from the manifest — there is NO dynamic code execution.
"""

from typing import Dict

from core.database import load_all_plugin_manifests, save_plugin_manifest
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

    # Persist (#269): every caller of this function reaches here, so this is the
    # single hook point that covers plugin install, manifest re-registration, and
    # startup restore alike -- the route survives a registry restart instead of
    # relying on in-memory state.
    await save_plugin_manifest(plugin_name, manifest)

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
        # Fail closed (#47): the manifest declares a secretRef, meaning this
        # webhook is meant to be authenticated, but no secrets store is wired to
        # verify it yet. Rejecting is the safe posture — silently accepting an
        # unverified request would be a security bypass.
        logger.warning(
            "Webhook for %s declares secretRef '%s' but secret verification is "
            "not implemented; rejecting (fail-closed).",
            plugin_name,
            secret_ref,
        )
        raise HTTPException(
            status_code=501,
            detail=(
                "Webhook secret verification is not implemented; requests that "
                "declare a secretRef are rejected until a secrets store is wired."
            ),
        )

    # Execute using execution engine
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

    Restores every persisted manifest from PostgreSQL (#269 — previously
    in-memory-only, backed by a "/tmp/*-manifest.yml" restart-safety
    workaround) and re-registers its webhook route. Only plugins still present
    in plugins_db are restored — a manifest whose plugin was since removed is
    left un-registered rather than resurrecting a stale route.
    """
    webhook_routes.clear()

    persisted = await load_all_plugin_manifests()
    logger.debug(f"Loaded {len(persisted)} persisted manifest(s) from PostgreSQL")

    for plugin_name, manifest in persisted.items():
        if plugin_name not in plugins_db:
            logger.debug(
                f"Skipping manifest for {plugin_name}: no longer in plugins_db"
            )
            continue
        plugin_manifests[plugin_name] = manifest
        try:
            await register_plugin_webhook(plugin_name, manifest)
        except Exception as e:
            # register_plugin_webhook re-persists the manifest it just loaded
            # (save_plugin_manifest now correctly raises on failure, #351-class
            # fix) -- that's a redundant re-write of data already known-good in
            # this exact table, so one transient DB hiccup here must not abort
            # restoring every OTHER plugin's webhook route on startup.
            logger.error(
                f"Failed to restore webhook route for {plugin_name} on startup: {e}"
            )

    logger.info(f"Restored {len(webhook_routes)} webhook routes on startup")
