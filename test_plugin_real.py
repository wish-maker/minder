#!/usr/bin/env python3
"""
Test if weather plugin actually works
"""

import sys

sys.path.insert(0, "/root/minder")

from pathlib import Path  # noqa: E402

# Test 1: Import plugin
print("=" * 60)
print("TEST 1: Import Weather Plugin")
print("=" * 60)

try:
    sys.path.insert(0, "/root/minder/plugins/weather")
    from weather_module import WeatherModule

    print("✓ Weather plugin imported successfully")
except Exception as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Create instance
print("\n" + "=" * 60)
print("TEST 2: Create Plugin Instance")
print("=" * 60)

try:
    plugin_config = {"plugins_path": Path("/root/minder/plugins")}
    plugin = WeatherModule(plugin_config)
    print("✓ Plugin instance created")
except Exception as e:
    print(f"✗ Instance creation failed: {e}")
    sys.exit(1)

# Test 3: Register plugin
print("\n" + "=" * 60)
print("TEST 3: Register Plugin")
print("=" * 60)

try:
    import asyncio

    async def test_register():
        metadata = await plugin.register()
        print(f"✓ Plugin registered: {metadata.name}")
        print(f"  - Version: {metadata.version}")
        print(f"  - Description: {metadata.description}")
        print(f"  - Capabilities: {metadata.capabilities}")
        return metadata

    metadata = asyncio.run(test_register())
except Exception as e:
    print(f"✗ Registration failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# Test 4: Health check
print("\n" + "=" * 60)
print("TEST 4: Health Check")
print("=" * 60)

try:

    async def test_health():
        health = await plugin.health_check()
        print(f"✓ Health check: {health['status']}")
        print(f"  - Healthy: {health.get('healthy', False)}")
        return health

    health = asyncio.run(test_health())
except Exception as e:
    print(f"✗ Health check failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL TESTS PASSED!")
print("=" * 60)
