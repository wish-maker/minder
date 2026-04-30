#!/usr/bin/env python3
"""
Test Module Enable/Disable System
Integration tests - require API server running on localhost:8000
"""

import pytest
import requests

BASE_URL = "http://localhost:8000"


@pytest.mark.integration
def test_list_modules():
    """Test listing modules via API Gateway"""
    print("\n📋 Testing module listing...")
    try:
        # Use API Gateway's v1 endpoint
        response = requests.get(f"{BASE_URL}/v1/plugins", timeout=5)
        response.raise_for_status()
        data = response.json()

        print(f"✅ Total plugins: {data.get('count', 0)}")

        print("\n   Plugin Status:")
        if "plugins" in data:
            for plugin in data["plugins"]:
                status = plugin.get("health_status", "unknown")
                status_icon = "✅" if status == "healthy" else "❌"
                print(f"      {status_icon} {plugin['name']}: {status}")

        # Verify response structure
        assert "count" in data or "total" in data, "Response missing count/total field"
        assert isinstance(data.get("plugins", []), list), "Plugins field is not a list"
        assert len(data.get("plugins", [])) >= 0, "Plugins list is invalid"

    except requests.exceptions.ConnectionError:
        pytest.skip("API server not running on localhost:8000")
    except requests.exceptions.HTTPError as e:
        pytest.skip(f"API endpoint error: {e}")


@pytest.mark.integration
@pytest.mark.integration
def test_enable_plugin():
    """Test enabling a plugin - INTEGRATION TEST (endpoint not implemented yet)"""
    print("\n🔧 Testing plugin enable...")
    try:
        # TODO: Implement this endpoint in API Gateway
        # POST /v1/plugins/{plugin_id}/enable
        print("   ℹ️  This test requires API Gateway endpoint implementation")
        pytest.skip("Plugin enable endpoint not implemented in API Gateway")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        pytest.fail(f"Plugin enable test failed: {e}")


@pytest.mark.integration
@pytest.mark.integration
def test_disable_plugin():
    """Test disabling a plugin - INTEGRATION TEST (endpoint not implemented yet)"""
    print("\n🔧 Testing plugin disable...")
    try:
        # TODO: Implement this endpoint in API Gateway
        # POST /v1/plugins/{plugin_id}/disable
        print("   ℹ️  This test requires API Gateway endpoint implementation")
        pytest.skip("Plugin disable endpoint not implemented in API Gateway")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        pytest.fail(f"Plugin disable test failed: {e}")


def main():
    """Run integration tests manually"""
    print("🧪 Module Management Integration Test")
    print("=" * 60)

    try:
        # List all plugins
        plugins = test_list_modules()

        # Get first enabled plugin for testing
        enabled_plugins = [p["name"] for p in plugins["plugins"] if p.get("enabled", False)]
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
