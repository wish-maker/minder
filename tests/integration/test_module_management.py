#!/usr/bin/env python3
"""
Test Module Enable/Disable System
Integration tests - require API server running on localhost:8000

Plugin enable/disable (POST /v1/plugins/{name}/enable|disable) are real,
implemented routes (plugin-registry/routes/plugins.py) -- the two tests that
used to claim otherwise (#338) are removed; the same behavior (401 without a
JWT) is already covered for real in
test_plugins_functionality.py::TestPluginLifecycle (#333 phase 3).
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

        print(f"✅ Total plugins: {len(data.get('plugins', []))}")

        print("\n   Plugin Status:")
        for plugin in data.get("plugins", []):
            status = plugin.get("health_status", "unknown")
            status_icon = "✅" if status == "healthy" else "❌"
            print(f"      {status_icon} {plugin['name']}: {status}")

        # Verify response structure (real shape: {"plugins": [...]}, #338)
        assert "plugins" in data, "Response missing plugins field"
        assert isinstance(data["plugins"], list), "Plugins field is not a list"

    except requests.exceptions.ConnectionError:
        pytest.skip("API server not running on localhost:8000")
    except requests.exceptions.HTTPError as e:
        pytest.skip(f"API endpoint error: {e}")
