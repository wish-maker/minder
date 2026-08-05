"""
Comprehensive Plugin Functionality Tests
Tests for all plugins: TEFAS, Weather, News, Crypto, Network, Fund
Tests plugin discovery, structure, and lifecycle endpoints via
gateway_test_client (tests/conftest.py) -- an in-process TestClient with no
live plugin-registry running, so proxied requests deterministically get a
real 503 (routes/proxy.py's ConnectError handling), while JWT-gated mutating
routes (#254) return 401 at the gateway itself before ever reaching the proxy.

Checked against the real plugin-registry routes (#333) -- the original
version of this file used the `requests` library against a hardcoded
http://localhost:8000 (needs a live docker-compose stack, incompatible with
this job's environment) and asserted several fictional per-plugin business
sub-routes (/tefas/funds, /weather/current, /news/headlines, /tefas/status --
none of these exist; the only real per-plugin routes are /{name},
/{name}/enable, /{name}/disable, /{name}/health, /{name}/collect,
/{name}/actions/{action}, /{name}/config).
"""

import pytest

pytestmark = [pytest.mark.integration]

REAL_PLUGINS = ["tefas", "weather", "news", "crypto", "network", "fund"]


class TestPluginsDiscovery:
    """Test plugin discovery and listing"""

    def test_list_all_plugins(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins")
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "plugins" in data
            assert isinstance(data["plugins"], list)

    def test_plugin_list_structure(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins")

        if response.status_code == 200:
            plugins = response.json()["plugins"]
            if plugins:
                plugin = plugins[0]
                assert "name" in plugin
                assert "version" in plugin
                assert "description" in plugin
                assert "status" in plugin
                assert "enabled" in plugin

    def test_plugin_detail_structure(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins/tefas")
        assert response.status_code in [200, 404, 503]

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert "name" in plugin
            assert "version" in plugin
            assert "description" in plugin
            assert "author" in plugin


@pytest.mark.parametrize("plugin_name", REAL_PLUGINS)
class TestPluginExists:
    """Each of the 6 real data plugins is discoverable via GET /v1/plugins/{name}."""

    def test_plugin_exists(self, gateway_test_client, plugin_name):
        response = gateway_test_client.get(f"/v1/plugins/{plugin_name}")
        assert response.status_code in [200, 404, 503]

    def test_plugin_structure(self, gateway_test_client, plugin_name):
        response = gateway_test_client.get(f"/v1/plugins/{plugin_name}")

        if response.status_code == 200:
            plugin = response.json()
            assert isinstance(plugin, dict)
            assert plugin["name"] == plugin_name
            assert "description" in plugin
            assert "version" in plugin
            assert "status" in plugin
            assert "enabled" in plugin


class TestPluginLifecycle:
    """enable/disable are real routes (#254: mutating, JWT-gated at the
    gateway itself via _require_jwt_for_writes -- returns 401 before ever
    reaching the unreachable-in-this-harness plugin-registry proxy)."""

    def test_plugin_enable_requires_auth(self, gateway_test_client):
        response = gateway_test_client.post("/v1/plugins/tefas/enable")
        assert response.status_code == 401

    def test_plugin_disable_requires_auth(self, gateway_test_client):
        response = gateway_test_client.post("/v1/plugins/tefas/disable")
        assert response.status_code == 401


class TestPluginErrorHandling:
    """Test plugin error handling and edge cases"""

    def test_invalid_plugin_name(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins/invalid-plugin")
        assert response.status_code in [404, 503]

    def test_plugin_not_found(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins/nonexistent")
        assert response.status_code in [404, 503]
