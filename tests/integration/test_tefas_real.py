#!/usr/bin/env python3
"""
Test TEFAS plugin with REAL API calls
"""
import asyncio
import sys

sys.path.insert(0, "/root/minder")

from plugins.tefas.tefas_module import TefasModule

config = {
    "database": {
        "host": "localhost",
        "port": 5432,
        "database": "fundmind",
        "user": "postgres",
        "password": "postgres",
    }
}


async def test_tefas_real():
    """Test TEFAS plugin with REAL API"""
    print("\n" + "=" * 60)
    print("📊 Testing TEFAS Plugin (REAL TEFAS API)")
    print("=" * 60)

    try:
        module = TefasModule(config)
        await module.register()

        # Try to fetch fund list from TEFAS
        print("Attempting to connect to TEFAS API...")

        # Test if TEFAS API is accessible
        import aiohttp

        async with aiohttp.ClientSession() as session:
            url = "https://www.tefas.org.tr"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                print(f"✅ TEFAS website reachable (HTTP {response.status})")

        # Test fund list endpoint
        fund_list_url = "https://www.tefas.org.tr/api/funds"
        async with aiohttp.ClientSession() as session:
            async with session.get(fund_list_url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ TEFAS API returning data!")
                    print(f"   Funds available: {len(data) if isinstance(data, list) else 'data received'}")
                    return True
                else:
                    print(f"⚠️  TEFAS API returned status {response.status}")
                    print("   This may be due to rate limiting or API changes")
                    return False

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_tefas_real())
    sys.exit(0 if result else 1)
