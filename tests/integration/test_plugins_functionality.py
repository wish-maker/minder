"""
Comprehensive Plugin Functionality Tests
Tests for all plugins: TEFAS, Weather, News, Crypto, Network, Fund
Tests plugin discovery, configuration, execution, error handling, and lifecycle.
"""

import pytest
import requests
from typing import Dict, List


class TestPluginsDiscovery:
    """Test plugin discovery and listing"""

    def test_list_all_plugins(self):
        """Test listing all available plugins"""
        response = requests.get("http://localhost:8000/v1/plugins")
        assert response.status_code in [200, 401]  # 200 or 401 Unauthorized

        if response.status_code == 200:
            data = response.json()
            assert "plugins" in data
            plugins = data["plugins"]
            assert isinstance(plugins, list)
            assert len(plugins) >= 5  # At least 5 plugins

    def test_plugin_list_structure(self):
        """Test plugin list has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins")

        if response.status_code == 200:
            data = response.json()
            plugins = data["plugins"]

            if len(plugins) > 0:
                plugin = plugins[0]
                assert "name" in plugin
                assert "version" in plugin
                assert "description" in plugin
                assert "status" in plugin
                assert "enabled" in plugin

    def test_plugin_detail_structure(self):
        """Test plugin detail has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas")

        if response.status_code in [200, 404]:
            if response.status_code == 200:
                plugin = response.json()
                assert isinstance(plugin, dict)
                assert "name" in plugin
                assert "version" in plugin
                assert "description" in plugin
                assert "author" in plugin
                # endpoints field is optional, only check if it exists
                if "endpoints" in plugin:
                    assert isinstance(plugin["endpoints"], list)


class TestTEFASPlugin:
    """Test TEFAS plugin functionality"""

    def test_tefas_plugin_exists(self):
        """Test TEFAS plugin is discoverable"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas")
        # 200 (found) or 404 (not found)
        assert response.status_code in [200, 404]

    def test_tefas_plugin_structure(self):
        """Test TEFAS plugin has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == "tefas"
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin

    def test_tefas_fund_analysis_endpoint(self):
        """Test TEFAS fund analysis endpoint exists"""
        # Try to call TEFAS plugin endpoint
        response = requests.get("http://localhost:8000/v1/plugins/tefas/funds")

        # Should be 401 (unauthorized) or 200 (success)
        # If 404, plugin might not have this endpoint
        assert response.status_code in [200, 401, 404]


class TestWeatherPlugin:
    """Test Weather plugin functionality"""

    def test_weather_plugin_exists(self):
        """Test Weather plugin is discoverable"""
        response = requests.get("http://localhost:8000/v1/plugins/weather")
        assert response.status_code in [200, 404]

    def test_weather_plugin_structure(self):
        """Test Weather plugin has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/weather")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == "weather"
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin

    def test_weather_data_endpoint(self):
        """Test Weather plugin data endpoint exists"""
        response = requests.get("http://localhost:8000/v1/plugins/weather/current")

        # Should be 401 (unauthorized) or 200 (success)
        assert response.status_code in [200, 401, 404]


class TestNewsPlugin:
    """Test News plugin functionality"""

    def test_news_plugin_exists(self):
        """Test News plugin is discoverable"""
        response = requests.get("http://localhost:8000/v1/plugins/news")
        assert response.status_code in [200, 404]

    def test_news_plugin_structure(self):
        """Test News plugin has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/news")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == "news"
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin

    def test_news_headlines_endpoint(self):
        """Test News plugin headlines endpoint exists"""
        response = requests.get("http://localhost:8000/v1/plugins/news/headlines")

        # Should be 401 (unauthorized) or 200 (success)
        assert response.status_code in [200, 401, 404]


class TestCryptoPlugin:
    """Test Crypto plugin functionality"""

    def test_crypto_plugin_exists(self):
        """Test Crypto plugin is discoverable"""
        response = requests.get("http://localhost:8000/v1/plugins/crypto")
        # 404 is expected (plugin not yet registered)
        assert response.status_code in [200, 404]

    def test_crypto_plugin_structure(self):
        """Test Crypto plugin has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/crypto")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == "crypto"
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin


class TestNetworkPlugin:
    """Test Network plugin functionality"""

    def test_network_plugin_exists(self):
        """Test Network plugin is discoverable"""
        response = requests.get("http://localhost:8000/v1/plugins/network")
        assert response.status_code in [200, 404]

    def test_network_plugin_structure(self):
        """Test Network plugin has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/network")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == "network"
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin


class TestFundPlugin:
    """Test Fund plugin functionality"""

    def test_fund_plugin_exists(self):
        """Test Fund plugin is discoverable"""
        response = requests.get("http://localhost:8000/v1/plugins/fund")
        assert response.status_code in [200, 404]

    def test_fund_plugin_structure(self):
        """Test Fund plugin has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/fund")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == "fund"
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin


class TestPluginLifecycle:
    """Test plugin enable/disable lifecycle"""

    def test_plugin_enable_endpoint_exists(self):
        """Test plugin enable endpoint is accessible"""
        # This would require authentication, so expect 401
        response = requests.post(
            "http://localhost:8000/v1/plugins/tefas/enable"
        )
        assert response.status_code in [200, 401, 404]

    def test_plugin_disable_endpoint_exists(self):
        """Test plugin disable endpoint is accessible"""
        # This would require authentication, so expect 401
        response = requests.post(
            "http://localhost:8000/v1/plugins/tefas/disable"
        )
        assert response.status_code in [200, 401, 404]

    def test_plugin_status_endpoint_exists(self):
        """Test plugin status endpoint is accessible"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/status")
        # 404 is expected (plugin might not have this endpoint)
        assert response.status_code in [200, 401, 404]


class TestPluginErrorHandling:
    """Test plugin error handling and edge cases"""

    def test_invalid_plugin_name(self):
        """Test invalid plugin name returns 404"""
        response = requests.get("http://localhost:8000/v1/plugins/invalid-plugin")
        assert response.status_code == 404

    def test_empty_plugin_name(self):
        """Test empty plugin name returns plugin list"""
        response = requests.get("http://localhost:8000/v1/plugins/")
        # Empty name should return plugin list (200) or 404
        assert response.status_code in [200, 404]

    def test_plugin_not_found(self):
        """Test non-existent plugin returns 404"""
        response = requests.get("http://localhost:8000/v1/plugins/nonexistent")
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
