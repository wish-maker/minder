#!/usr/bin/env python3
"""
TEFAS Module Simple Test
Core functionality test - minimal dependencies
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_imports():
    """Test if all imports work"""
    print("🔍 Testing imports...")
    try:
        from modules.tefas.tefas_module import TefasModule
        print("✅ TefasModule imported successfully")
        return True
    except Exception as e:
        print(f"❌ Import failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_metadata():
    """Test module metadata"""
    print("\n🔍 Testing metadata...")
    try:
        from modules.tefas.tefas_module import TefasModule

        config = {
            'database': {
                'host': 'localhost',
                'port': 5432,
                'database': 'fundmind',
                'user': 'postgres',
                'password': 'test'
            }
        }

        module = TefasModule(config)
        print("✅ Module instance created")
        return True
    except Exception as e:
        print(f"❌ Metadata test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_data_generation():
    """Test historical data generation"""
    print("\n🔍 Testing data generation...")
    try:
        from modules.tefas.tefas_module import TefasModule

        config = {
            'database': {
                'host': 'localhost',
                'port': 5432,
                'database': 'fundmind',
                'user': 'postgres',
                'password': 'test'
            }
        }

        module = TefasModule(config)

        # Test data generation (last 30 days)
        start_date = datetime.now() - timedelta(days=30)
        data = await module._generate_historical_data("TEST", start_date)

        print(f"✅ Generated {len(data)} data points")
        print(f"   Date range: {data[0]['date']} to {data[-1]['date']}")
        print(f"   Price range: {min(d['price'] for d in data):.2f} - {max(d['price'] for d in data):.2f}")

        return True
    except Exception as e:
        print(f"❌ Data generation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_module_structure():
    """Test module structure and methods"""
    print("\n🔍 Testing module structure...")
    try:
        from modules.tefas.tefas_module import TefasModule
        from core.module_interface import BaseModule

        config = {
            'database': {
                'host': 'localhost',
                'port': 5432,
                'database': 'fundmind',
                'user': 'postgres',
                'password': 'test'
            }
        }

        module = TefasModule(config)

        # Check if all required methods exist
        required_methods = [
            'register',
            'collect_data',
            'analyze',
            'train_ai',
            'index_knowledge',
            'get_correlations',
            'get_anomalies'
        ]

        missing_methods = []
        for method in required_methods:
            if not hasattr(module, method):
                missing_methods.append(method)

        if missing_methods:
            print(f"❌ Missing methods: {', '.join(missing_methods)}")
            return False

        print(f"✅ All {len(required_methods)} required methods present")
        return True
    except Exception as e:
        print(f"❌ Structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("🧪 TEFAS Module Simple Test")
    print("=" * 50)

    tests = [
        ("Imports", test_imports),
        ("Metadata", test_metadata),
        ("Structure", test_module_structure),
        ("Data Generation", test_data_generation)
    ]

    results = []
    for name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                result = asyncio.run(test_func())
            else:
                result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Test '{name}' crashed: {e}")
            results.append((name, False))

    print("\n" + "=" * 50)
    print("📊 Test Results:")
    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}  {name}")

    print(f"\n🎯 Summary: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
