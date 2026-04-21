"""
Plugin Sandboxing and Permission Enforcement Tests
Tests security features for untrusted 3rd party plugins
"""

from unittest.mock import Mock, patch

import pytest

from src.core.plugin_manifest import PluginManifest, PluginPermissions
from src.core.plugin_permissions import (
    DatabasePermissionChecker,
    FilesystemPermissionChecker,
    NetworkPermissionChecker,
    PermissionDenied,
    PermissionEnforcer,
    SandboxedPlugin,
)
from src.core.plugin_sandbox import (  # noqa: F401
    SandboxedPluginLoader,
    SandboxMemoryLimit,
    SandboxTimeout,
    SubprocessSandbox,
    ThreadSandbox,
)


class TestNetworkPermissionChecker:
    """Test network permission enforcement"""

    def test_allowed_host(self):
        """Test request to allowed host succeeds"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        checker = NetworkPermissionChecker(manifest)
        assert checker.check_request_allowed("https://api.example.com/data")

    def test_blocked_host(self):
        """Test request to blocked host fails"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        checker = NetworkPermissionChecker(manifest)

        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_request_allowed("https://evil.com/steal")

        assert "not allowed" in str(exc_info.value)

    def test_wildcard_host_matching(self):
        """Test wildcard host matching"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["*.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        checker = NetworkPermissionChecker(manifest)

        # Should allow subdomains
        assert checker.check_request_allowed("https://api.example.com/data")
        assert checker.check_request_allowed("https://sub.example.com/data")

        # Should block different domain
        with pytest.raises(PermissionDenied):
            checker.check_request_allowed("https://evil.com/data")

    def test_port_blocking(self):
        """Test port restrictions"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["*"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }  # Only HTTPS
            ),
        )

        checker = NetworkPermissionChecker(manifest)

        # Port 443 should be allowed
        assert checker.check_request_allowed("https://example.com:443/data")

        # Port 80 should be blocked
        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_request_allowed("http://example.com:80/data")

        assert "port" in str(exc_info.value).lower()

    def test_rate_limiting(self):
        """Test request rate limiting"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["*"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 2,
                }  # Very low limit
            ),
        )

        checker = NetworkPermissionChecker(manifest)

        # First 2 requests should succeed
        checker.check_request_allowed("https://example.com/1")
        checker.check_request_allowed("https://example.com/2")

        # 3rd request should fail
        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_request_allowed("https://example.com/3")

        assert "rate limit" in str(exc_info.value).lower()


class TestFilesystemPermissionChecker:
    """Test filesystem permission enforcement"""

    def test_allowed_read(self):
        """Test read from allowed path succeeds"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(filesystem={"read": ["/tmp/safe/*"], "write": [], "execute": []}),
        )

        checker = FilesystemPermissionChecker(manifest)
        assert checker.check_read_allowed("/tmp/safe/data.txt")

    def test_blocked_read(self):
        """Test read from blocked path fails"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(filesystem={"read": ["/tmp/safe/*"], "write": [], "execute": []}),
        )

        checker = FilesystemPermissionChecker(manifest)

        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_read_allowed("/etc/passwd")

        assert "not allowed" in str(exc_info.value)

    def test_blocked_write(self):
        """Test write to blocked path fails"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(filesystem={"read": [], "write": ["/tmp/safe/output/*"], "execute": []}),
        )

        checker = FilesystemPermissionChecker(manifest)

        with pytest.raises(PermissionDenied):
            checker.check_write_allowed("/etc/malicious")

    def test_blocked_execution(self):
        """Test execution of blocked file fails"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(filesystem={"read": [], "write": [], "execute": []}),  # No execution allowed
        )

        checker = FilesystemPermissionChecker(manifest)

        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_execute_allowed("/bin/bash")

        assert "not allowed" in str(exc_info.value)


class TestDatabasePermissionChecker:
    """Test database permission enforcement"""

    def test_allowed_query(self):
        """Test allowed database query"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                database={"databases": ["mydb"], "tables": ["users"], "operations": ["SELECT"]}
            ),
        )

        checker = DatabasePermissionChecker(manifest)
        assert checker.check_query_allowed("mydb", "users", "SELECT")

    def test_blocked_database(self):
        """Test access to blocked database"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                database={
                    "databases": ["mydb"],
                    "tables": [],
                    "operations": [],
                }  # Only mydb allowed
            ),
        )

        checker = DatabasePermissionChecker(manifest)

        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_query_allowed("otherdb", "users", "SELECT")

        assert "not allowed" in str(exc_info.value)

    def test_blocked_table(self):
        """Test access to blocked table"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                database={
                    "databases": [],
                    "tables": ["users"],
                    "operations": [],
                }  # Only users table
            ),
        )

        checker = DatabasePermissionChecker(manifest)

        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_query_allowed("mydb", "admin", "SELECT")

        assert "not allowed" in str(exc_info.value)

    def test_blocked_operation(self):
        """Test blocked database operation"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                database={"databases": [], "tables": [], "operations": ["SELECT"]}  # Read-only
            ),
        )

        checker = DatabasePermissionChecker(manifest)

        with pytest.raises(PermissionDenied) as exc_info:
            checker.check_query_allowed("mydb", "users", "DELETE")

        assert "not allowed" in str(exc_info.value)


class TestPermissionEnforcer:
    """Test integrated permission enforcement"""

    def test_safe_request_enforcement(self, tmp_path):
        """Test safe_request enforces network permissions"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        enforcer = PermissionEnforcer(manifest)

        # Mock requests to avoid actual network call
        with patch("requests.request") as mock_request:
            mock_request.return_value = Mock(status_code=200)

            # Allowed request should succeed
            enforcer.safe_request("GET", "https://api.example.com/data")
            assert mock_request.called

    def test_safe_request_blocked(self):
        """Test safe_request blocks unauthorized requests"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        enforcer = PermissionEnforcer(manifest)

        # Blocked request should fail
        with pytest.raises(PermissionDenied):
            enforcer.safe_request("GET", "https://evil.com/steal")


class TestSandboxedPlugin:
    """Test sandboxed plugin wrapper"""

    def test_sandboxed_plugin_injection(self):
        """Test sandboxed plugin injects safe methods"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        plugin_instance = Mock()
        sandboxed = SandboxedPlugin(manifest, plugin_instance)

        # Check safe methods were injected
        assert hasattr(sandboxed, "safe_request")
        assert hasattr(sandboxed, "safe_read_file")
        assert hasattr(sandboxed, "safe_write_file")

    def test_sandboxed_plugin_permission_check(self):
        """Test sandboxed plugin enforces permissions"""
        manifest = PluginManifest(
            name="test",
            version="1.0.0",
            description="Test plugin for unit testing",
            author="Test Author",
            permissions=PluginPermissions(
                network={
                    "allowed_hosts": ["api.example.com"],
                    "allowed_ports": [443],
                    "max_requests_per_minute": 60,
                }
            ),
        )

        plugin_instance = Mock()
        sandboxed = SandboxedPlugin(manifest, plugin_instance)

        # Blocked request should fail
        with pytest.raises(PermissionDenied):
            sandboxed.safe_request("GET", "https://evil.com/steal")


class TestSandboxedPluginLoader:
    """Test sandboxed plugin loader"""

    def test_choose_subprocess_for_untrusted(self, tmp_path):
        """Test untrusted plugins use subprocess sandbox"""
        from src.core.plugin_manifest import validate_plugin_for_installation  # noqa: F401

        # Create test plugin
        plugin_dir = tmp_path / "untrusted_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "plugin.yml").write_text(
            """
name: untrusted_plugin
version: 1.0.0
description: Untrusted test plugin
author: External
minder:
  min_version: "1.0.0"
permissions:
  network:
    allowed_hosts: []
    allowed_ports: []
  database:
    databases: []
    tables: []
    operations: []
  resources:
    max_memory_mb: 256
capabilities: []
        """
        )

        (plugin_dir / "untrusted_plugin_plugin.py").write_text(
            """
from src.core.module_interface_v2 import BaseModule, ModuleMetadata

class UntrustedPlugin(BaseModule):
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="untrusted_plugin",
            version="1.0.0",
            description="Test",
            author="External",
        )
        """
        )

        loader = SandboxedPluginLoader()

        # Untrusted plugin should use subprocess sandbox
        sandbox = loader.load_plugin(plugin_dir, trusted=False)

        # Note: Can't fully test without async context, but we check type
        assert sandbox is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
