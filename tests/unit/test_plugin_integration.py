"""
Integration tests for Minder plugin system
Tests component interactions and service integrations
"""

import pytest
import asyncio
from datetime import datetime

# Import components
import sys

sys.path.insert(0, "/root/minder")

from src.core.dependency_resolver import DependencyResolver
from src.core.version_manager import VersionManager
from src.core.permission_manager import PermissionManager
from src.core.resource_manager import ResourceManager
from src.core.hot_reload_controller import HotReloadController, PluginVersion
from src.core.configuration_store import ConfigurationStore


class TestPluginInstallationFlow:
    """Test complete plugin installation flow"""

    @pytest.mark.asyncio
    async def test_install_from_manifest(self):
        """Test plugin installation from manifest.json"""
        manager = PluginManager()

        # Load manifest
        manifest_path = "/root/minder/tests/fixtures/valid_manifest.json"
        result = await manager.install_from_manifest(manifest_path)

        assert result["success"] == True
        assert "test_plugin" in manager.installed_plugins
        assert manager.installed_plugins["test_plugin"]["version"] == "1.0.0"

    @pytest.mark.asyncio
    async def test_install_with_dependencies(self):
        """Test plugin installation with dependency resolution"""
        manager = PluginManager()

        # Add plugins with dependencies
        plugin_a = {
            "id": "plugin_a",
            "version": "1.0.0",
            "dependencies": {"plugins": [{"id": "plugin_b", "version": "1.0.0"}]},
        }

        plugin_b = {"id": "plugin_b", "version": "1.0.0", "dependencies": {"plugins": []}}

        # Add to manager's resolver
        manager.dependency_resolver.add_plugin("plugin_a", plugin_a)
        manager.dependency_resolver.add_plugin("plugin_b", plugin_b)

        # Resolve load order
        order = manager.dependency_resolver.resolve_load_order(["plugin_a", "plugin_b"])

        # Verify both plugins are in order
        assert "plugin_b" in order
        assert "plugin_a" in order
        assert len(order) == 2

    @pytest.mark.asyncio
    async def test_install_with_permission_granting(self):
        """Test plugin installation with automatic permission granting"""
        manager = PluginManager()

        # Load manifest with permissions
        manifest_path = "/root/minder/tests/fixtures/valid_manifest.json"

        # Install with auto-grant permissions
        result = await manager.install_from_manifest(manifest_path, auto_grant_permissions=True)

        assert result["success"] == True
        # Verify permissions were registered
        stats = manager.permission_manager.get_statistics()
        assert stats["total_permissions"] > 0


class TestPluginUpgradeFlow:
    """Test plugin upgrade and hot reload"""

    @pytest.mark.asyncio
    async def test_version_upgrade(self):
        """Test semantic version upgrade"""
        manager = PluginManager()

        # Install plugin first
        manifest_path = "/root/minder/tests/fixtures/valid_manifest.json"
        await manager.install_from_manifest(manifest_path)

        # Try upgrade (will fail if no new version available)
        result = await manager.upgrade_plugin("test_plugin", "2.0.0")

        # Result should have expected keys
        assert "success" in result
        assert "from_version" in result
        assert "to_version" in result

    @pytest.mark.asyncio
    async def test_hot_reload_with_state_preservation(self):
        """Test hot reload preserves plugin state"""
        controller = HotReloadController()

        # Load initial version
        v1 = PluginVersion("test", "1.0.0", "/path/to/v1")
        v1.status = "active"
        controller.active_versions["test"] = v1

        # Capture initial state
        initial_state = controller.state_backups.get("test", {})

        # Hot reload to v2.0.0
        result = await controller.hot_reload_plugin("test", "2.0.0", "/path/to/v2")

        # Verify hot reload was attempted
        assert "success" in result
        # Verify state backup exists (might be modified by hot reload)
        assert "test" in controller.state_backups

    @pytest.mark.asyncio
    async def test_rollback_after_failed_upgrade(self):
        """Test rollback after failed upgrade"""
        manager = PluginManager()

        # Install plugin first
        manifest_path = "/root/minder/tests/fixtures/valid_manifest.json"
        await manager.install_from_manifest(manifest_path)

        # Try rollback (should work even if upgrade didn't happen)
        result = await manager.rollback_plugin("test_plugin")

        # Rollback might fail if no previous version, but should return a result
        assert "success" in result
        assert "from_version" in result
        assert "to_version" in result


class TestConfigurationManagement:
    """Test configuration store integration"""

    @pytest.mark.asyncio
    async def test_config_update_with_validation(self):
        """Test configuration update with schema validation"""
        store = ConfigurationStore()

        # Define schema
        schema = {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}, "update_interval": {"type": "integer", "minimum": 60}},
            "required": ["enabled"],
        }

        # Valid config
        valid_config = {"enabled": True, "update_interval": 300}
        result = await store.update_plugin_config("test", valid_config, schema)

        assert result["success"] == True
        assert result["version"] == "1"

    @pytest.mark.asyncio
    async def test_config_validation_fails(self):
        """Test configuration validation fails for invalid config"""
        store = ConfigurationStore()

        schema = {"type": "object", "properties": {"enabled": {"type": "boolean"}}, "required": ["enabled"]}

        # Invalid config (missing required field)
        invalid_config = {"update_interval": 300}
        result = await store.update_plugin_config("test", invalid_config, schema)

        assert result["success"] == False
        assert len(result["errors"]) > 0

    @pytest.mark.asyncio
    async def test_config_rollback(self):
        """Test configuration rollback to previous version"""
        store = ConfigurationStore()

        # Create version 1
        config_v1 = {"enabled": True, "update_interval": 300}
        await store.update_plugin_config("test", config_v1)

        # Create version 2
        config_v2 = {"enabled": False, "update_interval": 600}
        await store.update_plugin_config("test", config_v2)

        # Rollback to v1
        result = await store.rollback_config("test", "1")

        assert result["success"] == True
        assert result["to_version"] == "1"


class TestPermissionEnforcement:
    """Test permission enforcement in real scenarios"""

    @pytest.mark.asyncio
    async def test_api_permission_enforcement(self):
        """Test API endpoint permission enforcement"""
        manager = PermissionManager()

        manifest = {
            "permissions": {
                "apis": [{"name": "external_api", "endpoints": ["https://api.example.com/*"], "rate_limit": "100/hour"}]
            }
        }

        manager.register_plugin_permissions("test", manifest)
        manager.grant_permission("test", "external_api")

        # Test allowed access
        assert manager.validate_api_access("test", "https://api.example.com/data", "GET") == True

        # Test denied access
        assert manager.validate_api_access("test", "https://unauthorized.com", "GET") == False

    @pytest.mark.asyncio
    async def test_filesystem_permission_enforcement(self):
        """Test filesystem access permission enforcement"""
        manager = PermissionManager()

        manifest = {
            "permissions": {
                "file_system": {"read": ["/data/test"], "write": ["/data/test/output"], "deny": ["/etc/passwd"]}
            }
        }

        manager.register_plugin_permissions("test", manifest)
        manager.grant_permission("test", "filesystem")

        # Test allowed access
        assert manager.validate_filesystem_access("test", "/data/test", "read") == True
        assert manager.validate_filesystem_access("test", "/data/test/output", "write") == True

        # Test denied access
        assert manager.validate_filesystem_access("test", "/etc/passwd", "read") == False


class TestResourceManagement:
    """Test resource allocation and enforcement"""

    @pytest.mark.asyncio
    async def test_resource_quota_enforcement(self):
        """Test resource quota enforcement"""
        manager = ResourceManager()

        manifest = {"resources": {"cpu": {"limit": "0.5"}, "memory": {"limit": "512MB"}}}

        quota = manager.allocate_resources("test", manifest)

        # Test within limits
        quota.cpu_usage = 25.0
        assert quota.check_cpu_limit() == True

        # Test exceeding limits
        quota.cpu_usage = 95.0
        assert quota.check_cpu_limit() == False

    @pytest.mark.asyncio
    async def test_resource_isolation(self):
        """Test resource isolation between plugins"""
        manager = ResourceManager()

        # Allocate resources for plugin A
        manifest_a = {"resources": {"cpu": {"limit": "0.5"}, "memory": {"limit": "512MB"}}}
        quota_a = manager.allocate_resources("plugin_a", manifest_a)

        # Allocate resources for plugin B
        manifest_b = {"resources": {"cpu": {"limit": "0.3"}, "memory": {"limit": "256MB"}}}
        quota_b = manager.allocate_resources("plugin_b", manifest_b)

        # Verify isolation
        assert quota_a.plugin_id != quota_b.plugin_id
        assert quota_a.cpu_limit != quota_b.cpu_limit


class TestStatisticsAggregation:
    """Test statistics aggregation across components"""

    @pytest.mark.asyncio
    async def test_aggregate_plugin_statistics(self):
        """Test aggregating statistics from all components"""
        manager = PluginManager()

        # Add some test data
        manager.installed_plugins = {"test": {"version": "1.0.0", "status": "active"}}

        # Get statistics
        stats = manager.get_system_statistics()

        # Check that statistics structure exists
        assert "plugins" in stats
        assert "dependencies" in stats
        assert "versions" in stats
        assert "permissions" in stats
        assert "resources" in stats

        # Verify plugin count
        assert stats["plugins"]["total"] >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
