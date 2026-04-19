#!/usr/bin/env python3
"""
Check which plugins are loaded in the kernel
"""

import asyncio
import os
import sys

sys.path.insert(0, "/root/minder")


async def check_plugins():
    """Check plugin status"""
    print("=" * 60)
    print("Plugin Status Check")
    print("=" * 60)

    from core.kernel import MinderKernel

    # Create config
    config = {
        "fund": {
            "database": {
                "host": "postgres",
                "port": 5432,
                "database": "fundmind",
                "user": "postgres",
                "password": os.getenv("POSTGRES_PASSWORD", "postgrespassword"),
            }
        },
        "plugins": {"network": {}, "weather": {}, "crypto": {}, "news": {}},
        "plugin_store": {
            "enabled": True,
            "store_path": "/app/plugins",
        },
    }

    # Create kernel
    print("\n1. Creating kernel...")
    kernel = MinderKernel(config)

    # Start kernel
    print("2. Starting kernel...")
    await kernel.start()

    # List plugins
    print("3. Listing plugins...")
    plugins = await kernel.registry.list_plugins()

    print(f"\n✓ Found {len(plugins)} plugins:")
    for plugin in plugins:
        print(f"  - {plugin['name']}")
        print(f"    Status: {plugin['status']}")
        print(f"    Version: {plugin['metadata']['version']}")
        print(f"    Description: {plugin['metadata']['description']}")
        print()

    # Check kernel registry directly
    print("4. Checking registry directly...")
    print(f"   Plugins in registry: {list(kernel.registry.plugins.keys())}")
    print(f"   Metadata in registry: {list(kernel.registry.metadata.keys())}")

    # Cleanup
    await kernel.stop()

    return plugins


if __name__ == "__main__":
    plugins = asyncio.run(check_plugins())
    print(f"\n✓ Total plugins loaded: {len(plugins)}")
