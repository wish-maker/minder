#!/usr/bin/env python3
"""
Test plugin installation by manually loading plugins
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, "/root/minder")

from core.config import MinderConfig
from plugins.store import PluginStore

async def test_plugin_store():
    """Test if plugin store can load existing plugins"""
    print("=" * 60)
    print("Testing Plugin Store Load Existing Plugins")
    print("=" * 60)

    # Create config
    config = {
        "enabled": True,
        "store_path": "/app/plugins",
    }

    # Create plugin store
    store = PluginStore(config)

    # Initialize (should load existing plugins)
    await store.initialize()

    # List installed plugins
    plugins = await store.list_installed_plugins()

    print(f"\n✓ Found {len(plugins)} plugins:")
    for plugin in plugins:
        print(f"  - {plugin['name']}: {plugin['description']}")
        print(f"    Version: {plugin['version']}")
        print(f"    Author: {plugin['author']}")

    return plugins

if __name__ == "__main__":
    plugins = asyncio.run(test_plugin_store())
