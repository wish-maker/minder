#!/usr/bin/env python3
"""
Test Module Enable/Disable System
Integration tests - require API server running on localhost:8000
"""
import requests
import json
import pytest

BASE_URL = "http://localhost:8000"


@pytest.mark.integration
def test_list_modules():
    """Test listing modules"""
    print("\n📋 Testing module listing...")
    try:
        response = requests.get(f"{BASE_URL}/plugins", timeout=5)
        response.raise_for_status()
        data = response.json()

        print(f"✅ Total plugins: {data['total']}")
        print(f"   - Enabled: {data['enabled']}")
        print(f"   - Disabled: {data['disabled']}")

        print("\n   Plugin Status:")
        for plugin in data['plugins']:
            status_icon = "✅" if plugin.get('enabled', False) else "❌"
            print(
                f"      {status_icon} {plugin['name']}: {plugin.get('enabled', False)}")

        return data
    except requests.exceptions.ConnectionError:
        pytest.skip("API server not running on localhost:8000")


@pytest.mark.integration
def test_enable_plugin():
    """Test enabling a plugin"""
    print("\n🔛 Testing plugin enable...")
    try:
        # Try to enable network plugin
        response = requests.post(
            f"{BASE_URL}/plugins/network/enable", timeout=5)
        response.raise_for_status()
        data = response.json()
        print(f"✅ {data.get('message', 'Plugin enabled')}")
        return data
    except requests.exceptions.ConnectionError:
        pytest.skip("API server not running on localhost:8000")


@pytest.mark.integration
def test_disable_plugin():
    """Test disabling a plugin"""
    print("\n🔴 Testing plugin disable...")
    try:
        # Try to disable network plugin
        response = requests.post(
            f"{BASE_URL}/plugins/network/disable", timeout=5)
        response.raise_for_status()
        data = response.json()
        print(f"✅ {data.get('message', 'Plugin disabled')}")
        return data
    except requests.exceptions.ConnectionError:
        pytest.skip("API server not running on localhost:8000")


def main():
    """Run integration tests manually"""
    print("🧪 Module Management Integration Test")
    print("=" * 60)

    try:
        # List all plugins
        plugins = test_list_modules()

        # Get first enabled plugin for testing
        enabled_plugins = [p['name']
                           for p in plugins['plugins'] if p.get('enabled', False)]
        # disabled_plugins = [
        #     p['name'] for p in plugins['plugins']
        #     if not p.get('enabled', False)]

        if enabled_plugins:
            test_plugin = enabled_plugins[0]
            print(f"\n📝 Testing with plugin: {test_plugin}")

            # Disable and re-enable
            test_disable_plugin()
            test_enable_plugin()

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
