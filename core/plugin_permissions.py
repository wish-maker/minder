"""
Plugin Permission Enforcement
Version: 1.0.0

Runtime enforcement of plugin permissions declared in plugin.yml
Ensures plugins can only access declared resources.
"""

import logging
import re
from pathlib import Path
from typing import List
from urllib.parse import urlparse

import requests

from core.plugin_manifest import PluginManifest, PluginPermissions

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    """Plugin attempted unauthorized operation"""

    pass


class NetworkPermissionChecker:
    """
    Enforces network access permissions

    Only allows requests to declared hosts/ports
    """

    def __init__(self, permissions: PluginPermissions):
        self.permissions = permissions.permissions
        self.request_count = 0
        self.last_request_time = None

    def check_request_allowed(self, url: str) -> bool:
        """
        Check if network request is allowed

        Args:
            url: Target URL

        Returns:
            True if allowed, False otherwise

        Raises:
            PermissionDenied: If request not allowed
        """
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Check rate limit
        self._check_rate_limit()

        # Check host whitelist
        allowed_hosts = self.permissions.network.allowed_hosts
        if allowed_hosts:
            if not self._is_host_allowed(host, allowed_hosts):
                raise PermissionDenied(
                    f"Network access to host '{host}' not allowed. " f"Allowed hosts: {allowed_hosts}"
                )

        # Check port whitelist
        allowed_ports = self.permissions.network.allowed_ports
        if allowed_ports and port not in allowed_ports:
            raise PermissionDenied(f"Network access to port {port} not allowed. " f"Allowed ports: {allowed_ports}")

        logger.debug(f"✓ Network request allowed: {url}")
        return True

    def _is_host_allowed(self, host: str, allowed_hosts: List[str]) -> bool:
        """Check if host is in allowed list"""
        # Exact match
        if host in allowed_hosts:
            return True

        # Wildcard matching
        for allowed in allowed_hosts:
            if "*" in allowed:
                # Convert wildcard to regex
                pattern = allowed.replace(".", r"\.").replace("*", ".*")
                if re.match(pattern, host):
                    return True

        return False

    def _check_rate_limit(self):
        """Enforce rate limiting"""
        max_requests = self.permissions.network.max_requests_per_minute

        if max_requests <= 0:
            return  # No limit

        import time

        current_time = time.time()

        # Reset counter every minute
        if self.last_request_time is None or (current_time - self.last_request_time) > 60:
            self.request_count = 0
            self.last_request_time = current_time

        # Check limit
        self.request_count += 1
        if self.request_count > max_requests:
            raise PermissionDenied(f"Rate limit exceeded: {self.request_count} requests per minute")


class FilesystemPermissionChecker:
    """
    Enforces filesystem access permissions

    Only allows access to declared paths
    """

    def __init__(self, permissions: PluginPermissions):
        self.permissions = permissions.permissions
        self._resolved_paths: dict = {}

    def check_read_allowed(self, filepath: str) -> bool:
        """
        Check if file read is allowed

        Args:
            filepath: Path to file

        Returns:
            True if allowed

        Raises:
            PermissionDenied: If read not allowed
        """
        allowed = self.permissions.filesystem.read

        if not allowed:
            # No read permissions at all
            raise PermissionDenied("Filesystem read access not allowed")

        # Check if path matches allowed patterns
        if not self._is_path_allowed(filepath, allowed):
            raise PermissionDenied(f"Read access to '{filepath}' not allowed. " f"Allowed paths: {allowed}")

        logger.debug(f"✓ File read allowed: {filepath}")
        return True

    def check_write_allowed(self, filepath: str) -> bool:
        """
        Check if file write is allowed

        Args:
            filepath: Path to file

        Returns:
            True if allowed

        Raises:
            PermissionDenied: If write not allowed
        """
        allowed = self.permissions.filesystem.write

        if not allowed:
            raise PermissionDenied("Filesystem write access not allowed")

        if not self._is_path_allowed(filepath, allowed):
            raise PermissionDenied(f"Write access to '{filepath}' not allowed. " f"Allowed paths: {allowed}")

        logger.debug(f"✓ File write allowed: {filepath}")
        return True

    def check_execute_allowed(self, filepath: str) -> bool:
        """
        Check if file execution is allowed

        Args:
            filepath: Path to executable

        Returns:
            True if allowed

        Raises:
            PermissionDenied: If execution not allowed
        """
        allowed = self.permissions.filesystem.execute

        if not allowed:
            raise PermissionDenied("Filesystem execute access not allowed")

        if not self._is_path_allowed(filepath, allowed):
            raise PermissionDenied(f"Execute access to '{filepath}' not allowed. " f"Allowed paths: {allowed}")

        logger.debug(f"✓ File execute allowed: {filepath}")
        return True

    def _is_path_allowed(self, filepath: str, allowed_patterns: List[str]) -> bool:
        """Check if path matches allowed patterns"""
        path = Path(filepath).resolve()

        for pattern in allowed_patterns:
            # Resolve pattern path
            if pattern not in self._resolved_paths:
                try:
                    self._resolved_paths[pattern] = Path(pattern).resolve()
                except Exception:
                    continue

            allowed_path = self._resolved_paths[pattern]

            # Check if path is within allowed path
            try:
                path.relative_to(allowed_path)
                return True
            except ValueError:
                # Not within allowed path
                pass

            # Wildcard matching
            if "*" in pattern:
                # Convert to regex
                regex_pattern = pattern.replace("*", ".*")
                if re.match(regex_pattern, str(path)):
                    return True

        return False


class DatabasePermissionChecker:
    """
    Enforces database access permissions

    Only allows access to declared databases/tables/operations
    """

    def __init__(self, permissions: PluginPermissions):
        self.permissions = permissions.permissions

    def check_query_allowed(self, database: str, table: str, operation: str) -> bool:
        """
        Check if database query is allowed

        Args:
            database: Database name
            table: Table name
            operation: Operation (SELECT, INSERT, UPDATE, DELETE, etc.)

        Returns:
            True if allowed

        Raises:
            PermissionDenied: If query not allowed
        """
        db_perms = self.permissions.database

        # Check database access
        allowed_dbs = db_perms.databases
        if allowed_dbs and database not in allowed_dbs:
            raise PermissionDenied(f"Database '{database}' not allowed. " f"Allowed databases: {allowed_dbs}")

        # Check table access
        allowed_tables = db_perms.tables
        if allowed_tables and table not in allowed_tables:
            raise PermissionDenied(f"Table '{table}' not allowed. " f"Allowed tables: {allowed_tables}")

        # Check operation
        allowed_ops = db_perms.operations
        if allowed_ops and operation.upper() not in [op.upper() for op in allowed_ops]:
            raise PermissionDenied(f"Operation '{operation}' not allowed. " f"Allowed operations: {allowed_ops}")

        logger.debug(f"✓ Database query allowed: " f"{database}.{table} ({operation})")
        return True


class PermissionEnforcer:
    """
    Main permission enforcement class

    Wraps all I/O operations with permission checks
    """

    def __init__(self, manifest: PluginManifest):
        self.manifest = manifest
        self.network = NetworkPermissionChecker(manifest)
        self.filesystem = FilesystemPermissionChecker(manifest)
        self.database = DatabasePermissionChecker(manifest)

    def safe_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """
        Enforced network request

        Raises:
            PermissionDenied: If request not allowed
        """
        self.network.check_request_allowed(url)
        return requests.request(method, url, **kwargs)

    def safe_read_file(self, filepath: str, mode: str = "r") -> str:
        """
        Enforced file read

        Raises:
            PermissionDenied: If read not allowed
        """
        self.filesystem.check_read_allowed(filepath)
        with open(filepath, mode) as f:
            return f.read()

    def safe_write_file(self, filepath: str, content: str, mode: str = "w"):
        """
        Enforced file write

        Raises:
            PermissionDenied: If write not allowed
        """
        self.filesystem.check_write_allowed(filepath)
        with open(filepath, mode) as f:
            f.write(content)

    def safe_execute(self, filepath: str, *args):
        """
        Enforced file execution

        Raises:
            PermissionDenied: If execution not allowed
        """
        self.filesystem.check_execute_allowed(filepath)
        import subprocess

        return subprocess.run([filepath] + list(args))

    def safe_db_query(self, database: str, table: str, operation: str, query_func, *args, **kwargs):
        """
        Enforced database query

        Args:
            database: Database name
            table: Table name
            operation: SQL operation
            query_func: Function to execute query

        Returns:
            Query result

        Raises:
            PermissionDenied: If query not allowed
        """
        self.database.check_query_allowed(database, table, operation)
        return query_func(*args, **kwargs)


class SandboxedPlugin:
    """
    Wrapper for plugins with enforced permissions

    Usage:
        plugin = SandboxedPlugin(manifest, plugin_instance)

        # All I/O operations are checked
        plugin.safe_request("GET", "https://api.example.com/data")
        plugin.safe_read_file("/tmp/safe/data.txt")
    """

    def __init__(self, manifest: PluginManifest, plugin_instance):
        self.manifest = manifest
        self.plugin = plugin_instance
        self.enforcer = PermissionEnforcer(manifest)

        # Inject safe methods into plugin
        self._inject_safe_methods()

    def _inject_safe_methods(self):
        """Inject permission-enforced methods into plugin"""
        self.plugin.safe_request = self.enforcer.safe_request
        self.plugin.safe_read_file = self.enforcer.safe_read_file
        self.plugin.safe_write_file = self.enforcer.safe_write_file
        self.plugin.safe_execute = self.enforcer.safe_execute
        self.plugin.safe_db_query = self.enforcer.safe_db_query

    def __getattr__(self, name):
        """Delegate all other attributes to plugin"""
        return getattr(self.plugin, name)


# Example usage
def example_permission_enforcement():
    """Example of permission enforcement"""
    from core.plugin_manifest import PluginManifest

    manifest_data = {
        "name": "example_plugin",
        "version": "1.0.0",
        "description": "Example",
        "author": "Test",
        "permissions": {
            "network": {
                "allowed_hosts": ["api.example.com"],
                "allowed_ports": [443],
                "max_requests_per_minute": 60,
            },
            "filesystem": {"read": ["/tmp/safe/*"], "write": ["/tmp/safe/output/*"], "execute": []},
            "database": {"databases": ["mydb"], "tables": ["users"], "operations": ["SELECT"]},
        },
    }

    manifest = PluginManifest(**manifest_data)
    plugin = SandboxedPlugin(manifest, plugin_instance=None)

    try:
        # ✓ Allowed - matches manifest
        plugin.safe_request("GET", "https://api.example.com/data")

        # ✗ Denied - different host
        plugin.safe_request("GET", "https://evil.com/steal")

    except PermissionDenied as e:
        print(f"Permission denied: {e}")


if __name__ == "__main__":
    example_permission_enforcement()
