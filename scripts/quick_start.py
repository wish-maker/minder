#!/usr/bin/env python3
"""
Minder Quick Start Script
Get Minder up and running in minutes
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.kernel import MinderKernel  # noqa: E402


async def quick_start():
    """Quick start Minder with default configuration"""
    print("=" * 60)
    print("MINDER QUICK START")
    print("=" * 60)
    print()

    # Default configuration
    config = {
        "plugins_path": "plugins",
        "plugin_store": {
            "enabled": True,
            "store_path": "/app/plugins",
        },
        "databases": {
            "postgres": {
                "host": "localhost",
                "port": 5432,
                "database": "minder",
                "user": "postgres",
                "password": "postgres",
            }
        },
        "plugins": {
            "weather": {},
            "news": {},
            "crypto": {},
            "network": {},
            "tefas": {},
        },
    }

    print("Configuration:")
    print("  Plugins: 5")
    print("  Store: Enabled")
    print("  Databases: PostgreSQL, InfluxDB, Qdrant, Redis")
    print()

    try:
        # Create kernel
        print("Creating kernel...")
        kernel = MinderKernel(config)

        # Start kernel
        print("Starting kernel...")
        await kernel.start()

        print("✓ Kernel started successfully")
        print()

        # Get system status
        print("System Status:")
        status = await kernel.get_system_status()

        print(f"  Status: {status['status']}")
        print(f"  Plugins: {status['plugins']['ready']}/{status['plugins']['total']} ready")
        print(f"  Correlations: {status['correlations']['total_correlations']}")
        print()

        print("Available endpoints:")
        print("  - http://localhost:8000/docs (API documentation)")
        print("  - http://localhost:8000/health (Health check)")
        print("  - http://localhost:8000/plugins (Plugin management)")
        print("  - http://localhost:8000/system/status (System status)")
        print()

        print("Quick commands:")
        print("  - Test plugins: curl http://localhost:8000/plugins")
        print("  - Run pipeline: curl -X POST http://localhost:8000/plugins/crypto/pipeline")
        print("  - Monitor: python3 scripts/monitoring_cli.py all")
        print()

        print("=" * 60)
        print("MINDER IS READY!")
        print("=" * 60)
        print()
        print("Press Ctrl+C to stop")

        # Keep running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping kernel...")
            await kernel.stop()
            print("✓ Kernel stopped")

    except Exception as e:
        print(f"✗ Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure Docker containers are running: docker compose up -d")
        print("  2. Check .env file is configured")
        print("  3. Verify database connections: docker compose ps")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(quick_start())
