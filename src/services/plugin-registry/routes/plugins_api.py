"""Plugin CRUD + lifecycle endpoints.

Built via a factory with shared state (plugins_db, plugin_instances, plugin_manifests,
webhook_routes, redis) and the main-owned helpers (update_plugin_in_database,
register_plugin_webhook, handle_webhook_request) injected — those helpers are also used
by startup/webhook-registration, so they stay in main. validate_manifest, auth deps and
PluginInfo are imported directly (no request state). Mirrors routes/services.py.
"""

import json
from datetime import datetime

import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from models import PluginInfo
from schemas.validator import validate_manifest

from shared.auth.jwt_middleware import enforce_rate_limit, get_current_user


def build_plugins_router(
    *,
    plugins_db,
    plugin_instances,
    plugin_manifests,
    webhook_routes,
    redis_client,
    update_plugin_in_database,
    register_plugin_webhook,
    handle_webhook_request,
    logger,
) -> APIRouter:
    router = APIRouter(tags=["Plugins"])

    @router.get("/plugins")
    async def list_plugins_redirect():
        """Redirect /plugins to /v1/plugins for backward compatibility"""
        return RedirectResponse(url="/v1/plugins", status_code=301)

    @router.get("/v1/plugins")
    async def list_plugins():
        """List all registered plugins (public endpoint)"""
        return {"plugins": list(plugins_db.values()), "count": len(plugins_db)}

    @router.get("/v1/plugins/{plugin_name}")
    async def get_plugin(plugin_name: str):
        """Get plugin details"""
        plugin = plugins_db.get(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        return plugin

    def _parse_manifest(body: bytes, content_type: str):
        is_yaml = (
            "yaml" in content_type
            or "yml" in content_type
            or body.strip().startswith(b"apiVersion")
        )
        try:
            return yaml.safe_load(body) if is_yaml else json.loads(body.decode())
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Failed to parse manifest: {e}"
            )

    @router.post("/v1/plugins/install")
    async def install_plugin(request: Request, background_tasks: BackgroundTasks):
        """Install a plugin from a manifest (manifest-based, no code execution)."""
        manifest = _parse_manifest(
            await request.body(), request.headers.get("content-type", "")
        )

        is_valid, errors = validate_manifest(manifest)
        if not is_valid:
            raise HTTPException(status_code=422, detail={"errors": errors})

        plugin_name = manifest.get("metadata", {}).get("name")
        if not plugin_name:
            raise HTTPException(
                status_code=400, detail="Plugin name required in metadata"
            )
        if plugin_name in plugins_db:
            raise HTTPException(
                status_code=409, detail=f"Plugin {plugin_name} already installed"
            )

        meta = manifest.get("metadata", {})
        try:
            await update_plugin_in_database(
                plugin_name,
                version=meta.get("version", "1.0.0"),
                description=meta.get("description", ""),
                author=meta.get("author", ""),
                status="registered",
                enabled=True,
            )
            plugin_manifests[plugin_name] = manifest
            logger.info(f"Stored manifest for plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"Failed to store manifest in database: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to store manifest: {e}"
            )

        try:
            await register_plugin_webhook(plugin_name, manifest)
            logger.info(f"Registered webhook route for plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"Failed to register webhook: {e}")

        plugins_db[plugin_name] = PluginInfo(
            name=plugin_name,
            version=meta.get("version", "1.0.0"),
            description=meta.get("description", ""),
            author=meta.get("author", ""),
            status="registered",
            enabled=True,
            registered_at=datetime.now().isoformat(),
        )

        return {
            "message": f"Plugin {plugin_name} installed successfully",
            "plugin": plugin_name,
            "webhook_path": manifest.get("spec", {})
            .get("trigger", {})
            .get("webhook", {})
            .get("path"),
        }

    @router.delete("/v1/plugins/{plugin_name}")
    async def uninstall_plugin(
        plugin_name: str, current_user: dict = Depends(get_current_user)
    ):
        """Uninstall a plugin"""
        if plugin_name not in plugins_db:
            raise HTTPException(status_code=404, detail="Plugin not found")
        if plugin_name in plugin_instances:
            await plugin_instances[plugin_name].shutdown()
            del plugin_instances[plugin_name]
        del plugins_db[plugin_name]
        redis_client.delete(f"plugin:{plugin_name}")
        return {"message": f"Plugin {plugin_name} uninstalled"}

    @router.post("/webhook/{path:path}")
    async def handle_webhook(path: str, request: Request):
        """Generic webhook handler; routes to the plugin registered for the path."""
        return await handle_webhook_request(f"/webhook/{path}", request)

    @router.post("/v1/plugins/{plugin_name}/enable")
    async def enable_plugin(
        plugin_name: str, current_user: dict = Depends(get_current_user)
    ):
        """Enable a plugin"""
        plugin = plugins_db.get(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        plugin.status = "enabled"
        if plugin_name in plugin_instances:
            from src.core.interface import ModuleStatus

            plugin_instances[plugin_name].status = ModuleStatus.READY
        await update_plugin_in_database(plugin_name, status="enabled", enabled=True)
        return {"message": f"Plugin {plugin_name} enabled"}

    @router.post("/v1/plugins/{plugin_name}/disable")
    async def disable_plugin(
        plugin_name: str, current_user: dict = Depends(get_current_user)
    ):
        """Disable a plugin"""
        plugin = plugins_db.get(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        plugin.status = "disabled"
        if plugin_name in plugin_instances:
            from src.core.interface import ModuleStatus

            plugin_instances[plugin_name].status = ModuleStatus.REGISTERED
        await update_plugin_in_database(plugin_name, status="disabled", enabled=False)
        return {"message": f"Plugin {plugin_name} disabled"}

    @router.post("/v1/plugins/reload-webhook")
    async def reload_plugin_webhook(request: Request):
        """Re-register a plugin's webhook route from an uploaded manifest."""
        manifest = _parse_manifest(
            await request.body(), request.headers.get("content-type", "")
        )

        is_valid, errors = validate_manifest(manifest)
        if not is_valid:
            raise HTTPException(status_code=422, detail={"errors": errors})

        plugin_name = manifest.get("metadata", {}).get("name")
        if not plugin_name:
            raise HTTPException(
                status_code=400, detail="Plugin name required in metadata"
            )
        if plugin_name not in plugins_db:
            raise HTTPException(
                status_code=404,
                detail=f"Plugin {plugin_name} not found. Install it first.",
            )

        plugin_manifests[plugin_name] = manifest
        logger.info(f"Reloaded manifest for plugin: {plugin_name}")
        try:
            await register_plugin_webhook(plugin_name, manifest)
            logger.info(f"Re-registered webhook route for plugin: {plugin_name}")
        except Exception as e:
            logger.error(f"Failed to re-register webhook: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to register webhook: {e}"
            )

        return {
            "message": f"Webhook re-registered for {plugin_name}",
            "webhook_path": f"/webhook{manifest['spec']['trigger']['webhook']['path']}",
            "registered_routes": list(webhook_routes.keys()),
        }

    @router.get("/v1/plugins/{plugin_name}/health")
    async def get_plugin_health(plugin_name: str):
        """Get plugin health status"""
        plugin = plugins_db.get(plugin_name)
        if not plugin:
            raise HTTPException(status_code=404, detail="Plugin not found")
        plugin_instance = plugin_instances.get(plugin_name)
        if not plugin_instance:
            return {
                "name": plugin_name,
                "health_status": plugin.health_status,
                "last_health_check": plugin.last_health_check,
                "message": "Plugin instance not available",
            }
        return await plugin_instance.health_check()

    @router.post("/v1/plugins/{plugin_name}/collect")
    @enforce_rate_limit(max_requests=10, window_minutes=1)
    async def trigger_plugin_collection(
        plugin_name: str,
        background_tasks: BackgroundTasks,
        current_user: dict = Depends(get_current_user),
    ):
        """Manually trigger a plugin's background data collection."""
        plugin = plugins_db.get(plugin_name)
        if not plugin:
            raise HTTPException(
                status_code=404, detail=f"Plugin '{plugin_name}' not found"
            )
        if plugin.status != "enabled":
            raise HTTPException(
                status_code=400,
                detail=f"Plugin '{plugin_name}' is not enabled. Current status: {plugin.status}",
            )
        plugin_instance = plugin_instances.get(plugin_name)
        if not plugin_instance:
            raise HTTPException(
                status_code=500, detail=f"Plugin '{plugin_name}' instance not available"
            )
        background_tasks.add_task(plugin_instance.collect_data)
        username = current_user.get("username", "unknown")
        logger.info(
            f"Data collection triggered for plugin: {plugin_name} | User: {username} "
            f"({current_user.get('role', 'unknown')}) | {datetime.utcnow().isoformat()}"
        )
        return {
            "message": f"Data collection triggered for {plugin_name}",
            "plugin": plugin_name,
            "status": "collecting",
            "triggered_by": username,
            "timestamp": datetime.utcnow().isoformat(),
            "note": "Collection runs in background. Check /health endpoint for results.",
        }

    return router
