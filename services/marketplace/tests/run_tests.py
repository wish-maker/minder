#!/usr/bin/env python3
"""
Test runner for marketplace database schema tests
Run with: python run_tests.py
"""
import asyncio
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_database_schema import test_database_schema_created

async def main():
    """Run the database schema test"""
    print("🧪 Testing Marketplace Database Schema...")
    print("=" * 60)

    try:
        await test_database_schema_created()
        print("\n✅ All tests passed!")
        return 0
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n💥 Error running tests: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
