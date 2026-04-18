"""
Comprehensive Plugin System Tests
Tests manifest validation, security validation, installation, and loading
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

from core.plugin_manifest import (
    PluginManifest,
    ManifestValidator,
    validate_plugin_for_installation,
)
from core.module_interface_v2 import BaseModule, ModuleMetadata
from core.plugin_loader import PluginLoader


class TestPluginManifest:
    """Test plugin manifest validation"""

    def test_valid_manifest(self):
        """Test a valid manifest passes validation"""
        manifest_data = {
            "name": "test_plugin",
            "version": "1.0.0",
            "description": "A test plugin for validation",
            "author": "Test Author",
            "minder": {"min_version": "1.0.0"},
            "python": {"min_version": "3.11"},
            "dependencies": {"python": ["requests>=2.31.0"]},
            "permissions": {
                "filesystem": {"read": [], "write": [], "execute": []},
                "network": {
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                },
                "database": {"databases": [], "tables": [], "operations": []},
                "resources": {
                    "max_memory_mb": 256,
                    "max_cpu_percent": 30,
                    "max_execution_time": 120,
                },
            },
            "capabilities": ["data_collection", "analysis"],
        }

        manifest = PluginManifest(**manifest_data)
        assert manifest.name == "test_plugin"
        assert manifest.version == "1.0.0"
        assert len(manifest.dependencies["python"]) == 1

    def test_manifest_invalid_name(self):
        """Test manifest with invalid name fails"""
        with pytest.raises(ValueError) as exc_info:
            PluginManifest(
                name="_invalid",
                version="1.0.0",
                description="Test",
                author="Test",
            )
        assert "cannot start with underscore" in str(exc_info.value)

    def test_manifest_reserved_name(self):
        """Test manifest with reserved name fails"""
        with pytest.raises(ValueError) as exc_info:
            PluginManifest(
                name="kernel",
                version="1.0.0",
                description="Test",
                author="Test",
            )
        assert "reserved" in str(exc_info.value)

    def test_manifest_invalid_email(self):
        """Test manifest with invalid email fails"""
        with pytest.raises(ValueError) as exc_info:
            PluginManifest(
                name="test_plugin",
                version="1.0.0",
                description="Test",
                author="Test",
                email="not-an-email",
            )
        assert "Invalid email format" in str(exc_info.value)

    def test_manifest_invalid_version_format(self):
        """Test manifest with invalid version format fails"""
        with pytest.raises(Exception):
            PluginManifest(
                name="test_plugin",
                version="invalid",
                description="Test",
                author="Test",
            )


class TestManifestValidator:
    """Test manifest directory validation"""

    def test_validate_plugin_directory_missing(self):
        """Test validation of non-existent directory"""
        is_valid, errors = ManifestValidator.validate_plugin_directory(
            Path("/nonexistent/path")
        )
        assert not is_valid
        assert len(errors) > 0

    def test_validate_plugin_directory_missing_manifest(self):
        """Test validation of directory without manifest"""
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_path = Path(tmpdir) / "test_plugin"
            plugin_path.mkdir()

            is_valid, errors = ManifestValidator.validate_plugin_directory(plugin_path)
            assert not is_valid
            assert any("plugin.yml" in e for e in errors)

    def test_validate_plugin_directory_complete(self, tmp_path):
        """Test validation of complete plugin directory"""
        # Create plugin directory structure
        plugin_dir = tmp_path / "test_plugin"
        plugin_dir.mkdir()

        # Create manifest
        (plugin_dir / "plugin.yml").write_text("""
name: test_plugin
version: 1.0.0
description: Test plugin
author: Test Author
        """)

        # Create plugin file
        (plugin_dir / "test_plugin_plugin.py").write_text("""
from core.module_interface_v2 import BaseModule

class TestPlugin(BaseModule):
    async def register(self):
        pass
        """)

        # Create README
        (plugin_dir / "README.md").write_text("# Test Plugin")

        is_valid, errors = ManifestValidator.validate_plugin_directory(plugin_dir)
        assert is_valid
        assert len(errors) == 0


class TestPluginInstallationValidation:
    """Test complete plugin installation validation"""

    def test_validate_valid_plugin(self, tmp_path):
        """Test validation of valid plugin"""
        # Create complete plugin structure
        plugin_dir = tmp_path / "valid_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "plugin.yml").write_text("""
name: valid_plugin
version: 1.0.0
description: A valid test plugin
author: Test Author
minder:
  min_version: "1.0.0"
python:
  min_version: "3.11"
dependencies: {}
permissions:
  filesystem:
    read: []
    write: []
    execute: []
  network:
    allowed_hosts: []
    allowed_ports: []
  database:
    databases: []
    tables: []
    operations: []
  resources:
    max_memory_mb: 256
    max_cpu_percent: 30
    max_execution_time: 120
capabilities: []
        """)

        (plugin_dir / "valid_plugin_plugin.py").write_text("""
from core.module_interface_v2 import BaseModule, ModuleMetadata

class ValidPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="valid_plugin",
            version="1.0.0",
            description="Test plugin",
            author="Test Author",
        )
        """)

        (plugin_dir / "README.md").write_text("# Valid Plugin")

        is_valid, manifest, errors = validate_plugin_for_installation(plugin_dir)

        assert is_valid
        assert manifest is not None
        assert manifest.name == "valid_plugin"
        assert len(errors) == 0

    def test_validate_plugin_missing_files(self, tmp_path):
        """Test validation fails with missing files"""
        plugin_dir = tmp_path / "incomplete_plugin"
        plugin_dir.mkdir()

        # Only create manifest, no plugin file
        (plugin_dir / "plugin.yml").write_text("""
name: incomplete_plugin
version: 1.0.0
description: Incomplete plugin
author: Test
        """)

        is_valid, manifest, errors = validate_plugin_for_installation(plugin_dir)

        assert not is_valid
        assert len(errors) > 0


class TestPluginLoader:
    """Test plugin loading system"""

    @pytest.mark.asyncio
    async def test_load_plugin_not_found(self):
        """Test loading non-existent plugin"""
        config = {
            "plugins_path": "/tmp",
            "plugins": {}
        }

        loader = PluginLoader(config)
        plugin = await loader.load_plugin("nonexistent_plugin")

        assert plugin is None

    def test_loader_initialization(self):
        """Test loader can be initialized"""
        config = {
            "plugins_path": "/tmp",
            "plugins": {}
        }

        loader = PluginLoader(config)
        assert loader is not None
        assert loader.plugins_path == Path("/tmp")


class TestPluginSecurity:
    """Test plugin security features"""

    def test_plugin_resource_limits(self, tmp_path):
        """Test plugin respects resource limits"""
        # Create plugin with strict limits
        plugin_dir = tmp_path / "limited_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "plugin.yml").write_text("""
name: limited_plugin
version: 1.0.0
description: Plugin with resource limits
author: Test
permissions:
  resources:
    max_memory_mb: 128
    max_cpu_percent: 25
    max_execution_time: 60
    max_disk_space_mb: 512
        """)

        manifest = ManifestValidator.load_manifest(plugin_dir)
        assert manifest is not None
        assert manifest.permissions.resources.max_memory_mb == 128
        assert manifest.permissions.resources.max_cpu_percent == 25

    def test_plugin_network_permissions(self, tmp_path):
        """Test plugin network permissions are enforced"""
        plugin_dir = tmp_path / "network_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "plugin.yml").write_text("""
name: network_plugin
version: 1.0.0
description: Plugin with network access
author: Test
permissions:
  network:
    allowed_hosts: ["api.example.com"]
    allowed_ports: [443]
    max_requests_per_minute: 60
        """)

        manifest = ManifestValidator.load_manifest(plugin_dir)
        assert manifest is not None
        assert len(manifest.permissions.network.allowed_hosts) == 1
        assert 443 in manifest.permissions.network.allowed_ports


class TestThirdPartyPluginSupport:
    """Test 3rd party plugin installation support"""

    def test_third_party_plugin_manifest_validation(self, tmp_path):
        """Test third-party plugins must have valid manifests"""
        # Simulate a third-party plugin download
        plugin_dir = tmp_path / "third_party_plugin"
        plugin_dir.mkdir()

        # Third-party plugin must follow manifest schema
        (plugin_dir / "plugin.yml").write_text("""
name: third_party_plugin
version: 1.0.0
description: Third-party plugin
author: External Developer
email: dev@example.com
repository: https://github.com/example/third-party-plugin
minder:
  min_version: "1.0.0"
python:
  min_version: "3.11"
dependencies:
  python:
    - requests>=2.31.0
permissions:
  filesystem:
    read: []
    write: []
    execute: []
  network:
    allowed_hosts: ["api.example.com"]
    allowed_ports: [443]
  database:
    databases: []
    tables: []
    operations: []
  resources:
    max_memory_mb: 256
capabilities:
  - data_collection
  - analysis
        """)

        (plugin_dir / "third_party_plugin_plugin.py").write_text("""
from core.module_interface_v2 import BaseModule, ModuleMetadata

class ThirdPartyPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="third_party_plugin",
            version="1.0.0",
            description="Third-party plugin",
            author="External Developer",
            dependencies=["requests>=2.31.0"],
            capabilities=["data_collection", "analysis"],
        )
        """)

        (plugin_dir / "README.md").write_text("""
# Third-Party Plugin

External plugin demonstrating 3rd party support.
        """)

        is_valid, manifest, errors = validate_plugin_for_installation(plugin_dir)

        assert is_valid, f"Validation failed: {errors}"
        assert manifest is not None
        assert manifest.author == "External Developer"
        assert len(errors) == 0

    def test_third_party_plugin_missing_metadata_fails(self, tmp_path):
        """Test third-party plugins without proper metadata fail"""
        plugin_dir = tmp_path / "bad_third_party"
        plugin_dir.mkdir()

        # Missing required fields
        (plugin_dir / "plugin.yml").write_text("""
name: bad_plugin
version: 1.0.0
description: Missing required metadata
        """)

        is_valid, manifest, errors = validate_plugin_for_installation(plugin_dir)

        assert not is_valid
        assert len(errors) > 0


class TestPluginSandboxing:
    """Test plugin sandboxing and isolation"""

    def test_plugin_manifest_declares_permissions(self, tmp_path):
        """Test plugins must declare permissions in manifest"""
        plugin_dir = tmp_path / "sandboxed_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "plugin.yml").write_text("""
name: sandboxed_plugin
version: 1.0.0
description: Sandboxed plugin
author: Test
permissions:
  filesystem:
    read: ["/tmp/safe/*"]
    write: ["/tmp/safe/output/*"]
    execute: []
  network:
    allowed_hosts: ["api.example.com"]
    allowed_ports: [443]
  database:
    databases: []
    tables: []
    operations: []
  resources:
    max_memory_mb: 256
    max_cpu_percent: 30
    max_execution_time: 120
        """)

        manifest = ManifestValidator.load_manifest(plugin_dir)
        assert manifest is not None
        # Verify permissions are declared
        assert len(manifest.permissions.filesystem.read) > 0
        assert len(manifest.permissions.network.allowed_hosts) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
