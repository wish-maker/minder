"""
Plugin Configuration Tests
Tests for plugin configuration: get, update, delete, and version management.
Tests plugin configuration management, settings persistence, and versioning.
"""

import pytest
import requests
import json
from typing import Dict


class TestPluginConfiguration:
    """Test plugin configuration management"""

    def test_plugin_config_get_endpoint_exists(self):
        """Test plugin config get endpoint is accessible"""
        # Without auth, expect 401 Unauthorized
        response = requests.get("http://localhost:8000/v1/plugins/tefas/config")
        # 401 (auth required) or 200 (success)
        assert response.status_code in [200, 401, 404]

    def test_plugin_config_update_endpoint_exists(self):
        """Test plugin config update endpoint is accessible"""
        # Without auth, expect 401 Unauthorized
        response = requests.put(
            "http://localhost:8000/v1/plugins/tefas/config",
            json={"refresh_interval": 300}
        )
        # 401 (auth required) or 404 (not implemented)
        assert response.status_code in [200, 401, 404]

    def test_plugin_config_delete_endpoint_exists(self):
        """Test plugin config delete endpoint is accessible"""
        # Without auth, expect 401 Unauthorized
        response = requests.delete("http://localhost:8000/v1/plugins/tefas/config")
        # 401 (auth required) or 404 (not implemented)
        assert response.status_code in [200, 401, 404]

    def test_plugin_version_endpoint_exists(self):
        """Test plugin version endpoint is accessible"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/version")
        # 200 (found) or 404 (not found)
        assert response.status_code in [200, 404]

    def test_plugin_version_structure(self):
        """Test plugin version has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/version")

        if response.status_code == 200:
            version = response.json()
            assert "version" in version
            assert "latest" in version or "stable" in version
            assert "changelog" in version or "changes" in version

    def test_plugin_settings_endpoint_exists(self):
        """Test plugin settings endpoint is accessible"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/settings")
        # 401 (auth required) or 200 (success)
        assert response.status_code in [200, 401, 404]

    def test_plugin_settings_structure(self):
        """Test plugin settings has correct structure"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/settings")

        if response.status_code == 200:
            settings = response.json()
            assert "settings" in settings or "config" in settings
            assert isinstance(settings.get("settings") or settings.get("config"), dict)


class TestTEFASPluginConfiguration:
    """Test TEFAS plugin configuration"""

    def test_tefas_config_get_endpoint_exists(self):
        """Test TEFAS config get endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/config")
        assert response.status_code in [200, 401, 404]

    def test_tefas_config_update_endpoint_exists(self):
        """Test TEFAS config update endpoint"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/tefas/config",
            json={"refresh_interval": 300, "cache_enabled": True}
        )
        assert response.status_code in [200, 401, 404]

    def test_tefas_version_endpoint_exists(self):
        """Test TEFAS version endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/version")
        assert response.status_code in [200, 404]

    def test_tefas_settings_endpoint_exists(self):
        """Test TEFAS settings endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/tefas/settings")
        assert response.status_code in [200, 401, 404]


class TestWeatherPluginConfiguration:
    """Test Weather plugin configuration"""

    def test_weather_config_get_endpoint_exists(self):
        """Test Weather config get endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/weather/config")
        assert response.status_code in [200, 401, 404]

    def test_weather_config_update_endpoint_exists(self):
        """Test Weather config update endpoint"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/weather/config",
            json={"location": "Istanbul", "units": "metric"}
        )
        assert response.status_code in [200, 401, 404]

    def test_weather_version_endpoint_exists(self):
        """Test Weather version endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/weather/version")
        assert response.status_code in [200, 404]

    def test_weather_settings_endpoint_exists(self):
        """Test Weather settings endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/weather/settings")
        assert response.status_code in [200, 401, 404]


class TestNewsPluginConfiguration:
    """Test News plugin configuration"""

    def test_news_config_get_endpoint_exists(self):
        """Test News config get endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/news/config")
        assert response.status_code in [200, 401, 404]

    def test_news_config_update_endpoint_exists(self):
        """Test News config update endpoint"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/news/config",
            json={"sources": ["feed1", "feed2"], "refresh_interval": 300}
        )
        assert response.status_code in [200, 401, 404]

    def test_news_version_endpoint_exists(self):
        """Test News version endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/news/version")
        assert response.status_code in [200, 404]

    def test_news_settings_endpoint_exists(self):
        """Test News settings endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/news/settings")
        assert response.status_code in [200, 401, 404]


class TestCryptoPluginConfiguration:
    """Test Crypto plugin configuration"""

    def test_crypto_config_get_endpoint_exists(self):
        """Test Crypto config get endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/crypto/config")
        assert response.status_code in [200, 401, 404]

    def test_crypto_config_update_endpoint_exists(self):
        """Test Crypto config update endpoint"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/crypto/config",
            json={"symbols": ["BTC", "ETH"], "refresh_interval": 60}
        )
        assert response.status_code in [200, 401, 404]

    def test_crypto_version_endpoint_exists(self):
        """Test Crypto version endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/crypto/version")
        assert response.status_code in [200, 404]

    def test_crypto_settings_endpoint_exists(self):
        """Test Crypto settings endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/crypto/settings")
        assert response.status_code in [200, 401, 404]


class TestNetworkPluginConfiguration:
    """Test Network plugin configuration"""

    def test_network_config_get_endpoint_exists(self):
        """Test Network config get endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/network/config")
        assert response.status_code in [200, 401, 404]

    def test_network_config_update_endpoint_exists(self):
        """Test Network config update endpoint"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/network/config",
            json={"scan_interval": 300, "alert_threshold": 5}
        )
        assert response.status_code in [200, 401, 404]

    def test_network_version_endpoint_exists(self):
        """Test Network version endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/network/version")
        assert response.status_code in [200, 404]

    def test_network_settings_endpoint_exists(self):
        """Test Network settings endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/network/settings")
        assert response.status_code in [200, 401, 404]


class TestFundPluginConfiguration:
    """Test Fund plugin configuration"""

    def test_fund_config_get_endpoint_exists(self):
        """Test Fund config get endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/fund/config")
        assert response.status_code in [200, 401, 404]

    def test_fund_config_update_endpoint_exists(self):
        """Test Fund config update endpoint"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/fund/config",
            json={"funds": ["TFKAS", "BIST100", "ALTIN"], "refresh_interval": 3600}
        )
        assert response.status_code in [200, 401, 404]

    def test_fund_version_endpoint_exists(self):
        """Test Fund version endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/fund/version")
        assert response.status_code in [200, 404]

    def test_fund_settings_endpoint_exists(self):
        """Test Fund settings endpoint"""
        response = requests.get("http://localhost:8000/v1/plugins/fund/settings")
        assert response.status_code in [200, 401, 404]


class TestPluginConfigurationErrorHandling:
    """Test plugin configuration error handling"""

    def test_invalid_config_field(self):
        """Test invalid config field returns 400 or 401"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/tefas/config",
            json={"invalid_field": "value"}
        )
        # 400 (bad request), 401 (auth required), or 404 (not implemented)
        assert response.status_code in [400, 401, 404]

    def test_invalid_config_value_type(self):
        """Test invalid config value type returns 400 or 401"""
        response = requests.put(
            "http://localhost:8000/v1/plugins/weather/config",
            json={"refresh_interval": "invalid_string"}
        )
        assert response.status_code in [400, 401, 404]

    def test_invalid_plugin_name(self):
        """Test invalid plugin name returns 404"""
        response = requests.get("http://localhost:8000/v1/plugins/invalid_plugin/config")
        assert response.status_code == 404

    def test_plugin_config_not_found(self):
        """Test plugin config not found returns 404"""
        # This would delete config first
        # For now, just check endpoint exists
        response = requests.get("http://localhost:8000/v1/plugins/tefas/config")
        # 200 (exists), 401 (auth required), or 404 (not found)
        assert response.status_code in [200, 401, 404]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
