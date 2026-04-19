#!/usr/bin/env python3
"""
Manually initialize plugin store and load plugins
"""

import asyncio
import sys

sys.path.insert(0, "/root/minder")


async def manual_init():
    """Manually initialize plugin store"""
    print("=" * 60)
    print("Manual Plugin Store Initialization")
    print("=" * 60)

    from plugins.store import PluginStore

    # Create config with correct path
    config_data = {
        "enabled": True,
        "store_path": "/app/plugins",  # Correct path
    }

    # Create store
    store = PluginStore(config_data)

    # Initialize
    await store.initialize()

    # List plugins
    plugins = await store.list_installed_plugins()

    print(f"\n✓ Loaded {len(plugins)} plugins:")
    for plugin in plugins:
        print(f"  - {plugin['name']}")
        print(f"    Version: {plugin['version']}")
        print(f"    Description: {plugin['description']}")

    return plugins


if __name__ == "__main__":
    plugins = asyncio.run(manual_init())
