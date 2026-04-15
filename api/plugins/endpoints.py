"""
Plugin management endpoints
Handles plugin discovery, loading, and management
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from typing import Optional
import logging

from ..models import PipelineRequest
from ..auth import get_current_user_optional
from ..middleware import limiter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plugins", tags=["Plugins"])


def setup_plugin_routes(router, kernel):
    """Setup plugin routes with kernel reference"""

    @router.get("")
    @limiter.limit("200/hour")  # Standard API endpoint
    async def list_plugins(
        request: Request,
        status: Optional[str] = None,
        current_user: dict = Depends(get_current_user_optional),
    ):
        """
        List all plugins

        Accessible from:
        - Trusted networks (local/VPN): No authentication required
        - Public networks: JWT authentication required

        Rate limited: 200/hour for VPN, 50/hour for public, unlimited for local
        """
        if not kernel:
            raise HTTPException(
                status_code=503, detail="Kernel not initialized"
            )

        plugins = await kernel.registry.list_plugins(status=status)

        # Add enabled status for each plugin
        for plugin in plugins:
            plugin_name = plugin["name"]
            plugin["enabled"] = kernel.registry.is_plugin_enabled(plugin_name)

        # Also list available but disabled plugins
        available_plugins = kernel.registry.list_available_plugins()
        loaded_plugin_names = {p["name"] for p in plugins}

        disabled_plugins = [
            {"name": name, "enabled": False, "status": "disabled"}
            for name in available_plugins
            if name not in loaded_plugin_names
        ]

        return {
            "plugins": plugins + disabled_plugins,
            "total": len(plugins) + len(disabled_plugins),
            "enabled": len(plugins),
            "disabled": len(disabled_plugins),
            "authenticated": current_user is not None,
            "network_type": (
                "trusted"
                if current_user and not current_user.get("authenticated", True)
                else "public"
            ),
        }

    @router.post("/{plugin_name}/pipeline")
    async def run_pipeline(
        pipeline_request: PipelineRequest, background_tasks: BackgroundTasks
    ):
        """Run pipeline on a plugin"""
        if not kernel:
            raise HTTPException(
                status_code=503, detail="Kernel not initialized"
            )

        try:
            results = await kernel.run_plugin_pipeline(
                pipeline_request.module, pipeline_request.pipeline
            )
            return {"plugin": pipeline_request.module, "results": results}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/{plugin_name}/enable")
    async def enable_plugin(plugin_name: str):
        """Enable a plugin at runtime"""
        if not kernel:
            raise HTTPException(
                status_code=503, detail="Kernel not initialized"
            )

        try:
            success = await kernel.registry.enable_plugin(plugin_name)
            if success:
                return {
                    "plugin": plugin_name,
                    "status": "enabled",
                    "message": f"Plugin {plugin_name} will be enabled on next restart",
                }
            else:
                raise HTTPException(
                    status_code=400, detail="Failed to enable plugin"
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @router.post("/{plugin_name}/disable")
    async def disable_plugin(plugin_name: str):
        """Disable a plugin at runtime"""
        if not kernel:
            raise HTTPException(
                status_code=503, detail="Kernel not initialized"
            )

        try:
            success = await kernel.registry.disable_plugin(plugin_name)
            if success:
                return {
                    "plugin": plugin_name,
                    "status": "disabled",
                    "message": f"Plugin {plugin_name} has been disabled and unloaded",
                }
            else:
                raise HTTPException(
                    status_code=400, detail="Failed to disable plugin"
                )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return router
