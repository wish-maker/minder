#!/usr/bin/env python3
"""
Test Module Enable/Disable System
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_list_modules():
    """Test listing modules"""
    print("\n📋 Testing module listing...")
    response = requests.get(f"{BASE_URL}/modules")
    data = response.json()

    print(f"✅ Total modules: {data['total']}")
    print(f"   - Enabled: {data['enabled']}")
    print(f"   - Disabled: {data['disabled']}")

    print("\n   Module Status:")
    for module in data['modules']:
        status_icon = "✅" if module['enabled'] else "❌"
        print(f"      {status_icon} {module['name']}: {module['enabled']}")

    return data

def test_enable_module(module_name):
    """Test enabling a module"""
    print(f"\n🔛 Enabling module: {module_name}")
    response = requests.post(f"{BASE_URL}/modules/{module_name}/enable")
    data = response.json()
    print(f"✅ {data['message']}")
    return data

def test_disable_module(module_name):
    """Test disabling a module"""
    print(f"\n🔴 Disabling module: {module_name}")
    response = requests.post(f"{BASE_URL}/modules/{module_name}/disable")
    data = response.json()
    print(f"✅ {data['message']}")
    return data

def main():
    print("🧪 Module Management Test")
    print("=" * 60)

    try:
        # List all modules
        modules = test_list_modules()

        # Get first enabled module for testing
        enabled_modules = [m['name'] for m in modules['modules'] if m['enabled']]
        disabled_modules = [m['name'] for m in modules['modules'] if not m['enabled']]

        if enabled_modules:
            test_module = enabled_modules[0]
            print(f"\n📝 Testing with module: {test_module}")

            # Disable and re-enable
            test_disable_module(test_module)
            test_enable_module(test_module)

            # List again to verify
            test_list_modules()

        print("\n" + "=" * 60)
        print("🎉 Module management test completed!")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
