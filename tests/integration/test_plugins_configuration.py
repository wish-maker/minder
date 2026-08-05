"""
Plugin Configuration Tests
Tests GET/PUT /v1/plugins/{name}/config via gateway_test_client
(tests/conftest.py) -- an in-process TestClient with no live plugin-registry
running, so GET proxies deterministically get a real 503 (routes/proxy.py's
ConnectError handling), while PUT (mutating) returns 401 at the gateway
itself before ever reaching the proxy (#254's JWT gate).

Checked against the real plugin-registry routes (#333) -- the original
version of this file used the `requests` library against a hardcoded
http://localhost:8000 (needs a live docker-compose stack) and asserted
/version and /settings endpoints for every plugin that don't exist anywhere
in plugins.py (only GET/PUT /config and DELETE is not implemented at all).
"""

import pytest

pytestmark = [pytest.mark.integration]

REAL_PLUGINS = ["tefas", "weather", "news", "crypto", "network", "fund"]


@pytest.mark.parametrize("plugin_name", REAL_PLUGINS)
class TestPluginConfiguration:
    """GET/PUT /v1/plugins/{name}/config for each of the 6 real data plugins."""

    def test_config_get(self, gateway_test_client, plugin_name):
        response = gateway_test_client.get(f"/v1/plugins/{plugin_name}/config")
        assert response.status_code in [200, 404, 503]

    def test_config_update_requires_auth(self, gateway_test_client, plugin_name):
        response = gateway_test_client.put(
            f"/v1/plugins/{plugin_name}/config",
            json={"refresh_interval": 300},
        )
        assert response.status_code == 401


class TestPluginConfigurationErrorHandling:
    """Test plugin configuration error handling"""

    def test_invalid_config_field_requires_auth(self, gateway_test_client):
        """A PUT is JWT-gated at the gateway before the body is ever
        inspected -- 401, not 400, regardless of the field's validity."""
        response = gateway_test_client.put(
            "/v1/plugins/tefas/config",
            json={"invalid_field": "value"},
        )
        assert response.status_code == 401

    def test_invalid_plugin_name(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins/invalid_plugin/config")
        assert response.status_code in [404, 503]

    def test_plugin_config_not_found(self, gateway_test_client):
        response = gateway_test_client.get("/v1/plugins/nonexistent/config")
        assert response.status_code in [404, 503]
