"""
Plugin Registry Routes for Merged Service
Basic CRUD operations for plugin management
"""
import logging
import sys
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Add parent directory to path for imports
sys.path.insert(0, '/app')
from config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)

router = APIRouter(tags=["Plugins"])


class Plugin(BaseModel):
    """Plugin model"""
    id: str
    name: str
    version: str
    description: str
    author: str
    status: str = "active"
    created_at: datetime = datetime.utcnow()


# In-memory plugin storage (would be database in production)
_plugins_db: Dict[str, Plugin] = {
    "example-plugin": Plugin(
        id="example-plugin",
        name="Example Plugin",
        version="1.0.0",
        description="An example plugin for demonstration",
        author="Minder Team"
    )
}


@router.get("/")
async def list_plugins():
    """
    List all registered plugins
    """
    logger.info("Listing all plugins")
    return {
        "plugins": list(_plugins_db.values()),
        "count": len(_plugins_db)
    }


@router.get("/{plugin_id}")
async def get_plugin(plugin_id: str):
    """
    Get plugin by ID
    """
    plugin = _plugins_db.get(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")
    return plugin


@router.post("/")
async def create_plugin(plugin: Plugin):
    """
    Create a new plugin
    """
    if plugin.id in _plugins_db:
        raise HTTPException(status_code=400, detail=f"Plugin {plugin.id} already exists")

    _plugins_db[plugin.id] = plugin
    logger.info(f"Created plugin: {plugin.id}")
    return plugin


@router.put("/{plugin_id}")
async def update_plugin(plugin_id: str, plugin: Plugin):
    """
    Update an existing plugin
    """
    if plugin_id not in _plugins_db:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

    _plugins_db[plugin_id] = plugin
    logger.info(f"Updated plugin: {plugin_id}")
    return plugin


@router.delete("/{plugin_id}")
async def delete_plugin(plugin_id: str):
    """
    Delete a plugin
    """
    if plugin_id not in _plugins_db:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

    del _plugins_db[plugin_id]
    logger.info(f"Deleted plugin: {plugin_id}")
    return {"message": f"Plugin {plugin_id} deleted successfully"}


@router.post("/{plugin_id}/install")
async def install_plugin(plugin_id: str):
    """
    Install a plugin
    """
    if plugin_id in _plugins_db:
        raise HTTPException(status_code=400, detail=f"Plugin {plugin_id} already installed")

    # Simulate plugin installation
    new_plugin = Plugin(
        id=plugin_id,
        name=f"Plugin {plugin_id}",
        version="1.0.0",
        description=f"Auto-installed plugin {plugin_id}",
        author="Unknown"
    )

    _plugins_db[plugin_id] = new_plugin
    logger.info(f"Installed plugin: {plugin_id}")
    return new_plugin


@router.post("/{plugin_id}/uninstall")
async def uninstall_plugin(plugin_id: str):
    """
    Uninstall a plugin
    """
    if plugin_id not in _plugins_db:
        raise HTTPException(status_code=404, detail=f"Plugin {plugin_id} not found")

    del _plugins_db[plugin_id]
    logger.info(f"Uninstalled plugin: {plugin_id}")
    return {"message": f"Plugin {plugin_id} uninstalled successfully"}
