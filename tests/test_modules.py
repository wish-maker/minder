"""
Minder Plugin Tests
Example test suite for plugin validation
"""

import pytest
from plugins.tefas.tefas_module import TefasModule
from plugins.network.network_module import NetworkModule


class TestTefasPlugin:
    """Test suite for TEFAS plugin"""

    @pytest.fixture
    def tefas_plugin(self):
        """Create TEFAS plugin instance"""
        config = {
            "database": {
                "host": "postgres",
                "port": 5432,
                "database": "minder_tefas",
                "user": "postgres",
                "password": "test",
            }
        }
        plugin = TefasModule(config)
        return plugin

    def test_plugin_registration(self, tefas_plugin):
        """Test plugin registration (synchronous)"""
        # Just test that the plugin can be instantiated
        assert tefas_plugin is not None
        assert hasattr(tefas_plugin, "register")

    def test_plugin_has_required_methods(self, tefas_plugin):
        """Test plugin has required methods"""
        assert hasattr(tefas_plugin, "collect_data")
        assert hasattr(tefas_plugin, "analyze")
        assert hasattr(tefas_plugin, "register")


class TestNetworkPlugin:
    """Test suite for Network plugin"""

    @pytest.fixture
    def network_plugin(self):
        """Create Network plugin instance"""
        config = {
            "influxdb": {
                "host": "influxdb",
                "port": 8086,
                "database": "minder",
            }
        }
        plugin = NetworkModule(config)
        return plugin

    def test_plugin_registration(self, network_plugin):
        """Test plugin registration (synchronous)"""
        assert network_plugin is not None
        assert hasattr(network_plugin, "register")

    def test_plugin_has_required_methods(self, network_plugin):
        """Test plugin has required methods"""
        assert hasattr(network_plugin, "collect_data")
        assert hasattr(network_plugin, "analyze")
        assert hasattr(network_plugin, "register")
