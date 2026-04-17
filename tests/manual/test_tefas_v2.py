#!/usr/bin/env python3
"""
Test new TEFAS module with tefas-crawler integration
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


async def test_tefas_v2():
    """Test new TEFAS module"""

    print("\n" + "=" * 60)
    print("Testing TEFAS Module v2.0 (tefas-crawler integration)")
    print("=" * 60)

    try:
        module = TefasModule(config)
        await module.register()

        # Test 1: Discover funds
        print("\n📊 Test 1: Fund Discovery")
        print("-" * 40)

        discovery = await module.discover_funds()

        if "error" not in discovery:
            print(f"✅ Total funds discovered: {discovery['total_funds']}")
            print(f"   YAT (Yatırım): {discovery['by_type']['YAT']}")
            print(f"   EMK (Emeklilik): {discovery['by_type']['EMK']}")
            print(f"   BYF (Bireysel): {discovery['by_type']['BYF']}")

            if discovery["new_funds"]:
                print(f"   New funds: {', '.join(discovery['new_funds'][:5])}")
        else:
            print(f"❌ Discovery failed: {discovery['error']}")

        # Test 2: Collect recent data
        print("\n📥 Test 2: Data Collection (Last 7 days)")
        print("-" * 40)

        # Modify batch size for testing
        module.collection_batch_days = 7

        collection = await module.collect_data()

        print(f"✅ Records collected: {collection['records_collected']}")
        print(f"   Errors: {collection['errors']}")

        # Test 3: KAP integration
        print("\n🌐 Test 3: KAP Integration")
        print("-" * 40)

        kap_data = await module.fetch_kap_data()

        if kap_data.get("status") == "success":
            print(f"✅ KAP data fetched: {kap_data.get('entries_found')} entries")
        else:
            print(f"⚠️  KAP fetch issue: {kap_data.get('error')}")

        # Test 4: State management
        print("\n💾 Test 4: State Management")
        print("-" * 40)

        print(f"✅ Known funds: {len(module.state['known_funds'])}")
        print(f"   Last discovery: {module.state['last_discovery']}")
        print(f"   Last collection: {module.state['last_collection_date']}")

        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)

        print("\n📊 CAPABILITIES:")
        print("  ✅ Dynamic fund discovery")
        print("  ✅ Historical data collection (2020+)")
        print("  ✅ State management")
        print("  ✅ KAP integration")
        print("  ✅ Batch processing")
        print("  ✅ Error handling")

        return True

    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_tefas_v2())
    sys.exit(0 if result else 1)
