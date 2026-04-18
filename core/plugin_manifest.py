# Minder Plugin Manifest Validator
# Version: 1.0.0

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


class FilesystemPermission(BaseModel):
    """File system permission configuration"""

    read: List[str] = Field(default_factory=list)
    write: List[str] = Field(default_factory=list)
    execute: List[str] = Field(default_factory=list)


class NetworkPermission(BaseModel):
    """Network permission configuration"""

    allowed_hosts: List[str] = Field(default_factory=list)
    allowed_ports: List[int] = Field(default_factory=list)
    max_requests_per_minute: int = 60


class DatabasePermission(BaseModel):
    """Database permission configuration"""

    databases: List[str] = Field(default_factory=list)
    tables: List[str] = Field(default_factory=list)
    operations: List[str] = Field(default_factory=list)


class ResourceLimits(BaseModel):
    """Resource limit configuration"""

    max_memory_mb: int = 512
    max_cpu_percent: int = 50
    max_execution_time: int = 300
    max_disk_space_mb: int = 1024


class PluginPermissions(BaseModel):
    """Plugin permissions"""

    filesystem: FilesystemPermission = Field(default_factory=FilesystemPermission)
    network: NetworkPermission = Field(default_factory=NetworkPermission)
    database: DatabasePermission = Field(default_factory=DatabasePermission)
    resources: ResourceLimits = Field(default_factory=ResourceLimits)


class PluginManifest(BaseModel):
    """
    Plugin manifest validator

    Validates plugin.yml manifest files before installation
    """

    # Metadata
    name: str = Field(..., min_length=2, max_length=50, pattern="^[a-z_][a-z0-9_]*$")
    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(..., min_length=10, max_length=500)
    author: str = Field(..., min_length=2, max_length=100)
    license: str = Field(default="MIT")
    email: Optional[str] = None
    repository: Optional[str] = None

    # Compatibility
    minder: Dict[str, str] = Field(default_factory=lambda: {"min_version": "1.0.0"})
    python: Dict[str, str] = Field(default_factory=lambda: {"min_version": "3.11"})

    # Dependencies
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)

    # Configuration
    configuration: Dict[str, Any] = Field(default_factory=dict)

    # Permissions
    permissions: PluginPermissions = Field(default_factory=PluginPermissions)

    # Capabilities
    capabilities: List[str] = Field(default_factory=list)

    # Data sources
    data_sources: List[Dict[str, Any]] = Field(default_factory=list)

    # Health check
    health_check: Dict[str, Any] = Field(default_factory=dict)

    # Security
    security: Dict[str, Any] = Field(
        default_factory=lambda: {
            "signature": {"required": False},
            "scan_on_install": True,
            "sandbox": {"required": True, "type": "subprocess"},
        }
    )

    # Lifecycle hooks
    hooks: Dict[str, List[str]] = Field(
        default_factory=lambda: {"pre_install": [], "post_install": [], "pre_uninstall": [], "post_uninstall": []}
    )

    # Testing
    testing: Dict[str, Any] = Field(default_factory=dict)

    # Documentation
    documentation: Dict[str, str] = Field(default_factory=dict)

    @field_validator("name")
    def validate_name(cls, v):
        """Validate plugin name"""
        if v.startswith("_"):
            raise ValueError("Plugin name cannot start with underscore")
        if v in ["system", "core", "kernel", "minder"]:
            raise ValueError(f"Plugin name '{v}' is reserved")
        return v

    @field_validator("email")
    def validate_email(cls, v):
        """Validate email format"""
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v

    @field_validator("capabilities")
    def validate_capabilities(cls, v):
        """Validate capabilities are known"""
        valid_capabilities = {
            "data_collection",
            "analysis",
            "visualization",
            "notifications",
            "storage",
            "authentication",
            "monitoring",
        }

        for cap in v:
            if cap not in valid_capabilities:
                logger.warning(f"Unknown capability: {cap}")
        return v

    @field_validator("dependencies")
    def validate_dependencies(cls, v):
        """Validate dependencies structure"""
        valid_keys = {"python", "system", "plugins"}

        for key in v.keys():
            if key not in valid_keys:
                raise ValueError(f"Unknown dependency type: {key}")

        return v


class ManifestValidator:
    """Validates plugin manifests"""

    @staticmethod
    def load_manifest(plugin_path: Path) -> Optional[PluginManifest]:
        """
        Load and validate plugin manifest

        Args:
            plugin_path: Path to plugin directory

        Returns:
            PluginManifest if valid, None if not found
        """
        manifest_path = plugin_path / "plugin.yml"

        if not manifest_path.exists():
            logger.error(f"Plugin manifest not found: {manifest_path}")
            return None

        try:
            with open(manifest_path) as f:
                manifest_data = yaml.safe_load(f)

            manifest = PluginManifest(**manifest_data)
            logger.info(f"✅ Valid plugin manifest: {manifest.name} v{manifest.version}")

            return manifest

        except Exception as e:
            logger.error(f"❌ Invalid plugin manifest: {e}")
            return None

    @staticmethod
    def validate_plugin_directory(plugin_path: Path) -> Tuple[bool, List[str]]:
        """
        Validate plugin directory structure

        Args:
            plugin_path: Path to plugin directory

        Returns:
            (is_valid, list of error messages)
        """
        errors = []

        # Check directory exists
        if not plugin_path.exists():
            return False, ["Plugin directory does not exist"]

        # Check for manifest
        manifest_path = plugin_path / "plugin.yml"
        if not manifest_path.exists():
            errors.append("Missing plugin.yml manifest")

        # Check for main plugin file
        plugin_name = plugin_path.name
        possible_files = [
            plugin_path / f"{plugin_name}_plugin.py",
            plugin_path / f"{plugin_name}_module.py",
            plugin_path / "__init__.py",
        ]

        if not any(f.exists() for f in possible_files):
            errors.append(f"No plugin file found ({plugin_name}_plugin.py or {plugin_name}_module.py)")

        # Check for README
        readme_path = plugin_path / "README.md"
        if not readme_path.exists():
            errors.append("Missing README.md (recommended)")

        is_valid = len(errors) == 0
        return is_valid, errors


def validate_plugin_for_installation(plugin_path: Path) -> Tuple[bool, PluginManifest, List[str]]:
    """
    Complete validation for plugin installation

    Args:
        plugin_path: Path to plugin directory

    Returns:
        (is_valid, manifest, list of error messages)
    """
    errors = []

    # Validate directory structure
    structure_valid, structure_errors = ManifestValidator.validate_plugin_directory(plugin_path)
    if not structure_valid:
        errors.extend(structure_errors)

    # Load and validate manifest
    manifest = ManifestValidator.load_manifest(plugin_path)
    if manifest is None:
        errors.append("Could not load plugin manifest")
        return False, None, errors

    # Check Minder version compatibility (optional - skip if config not available)
    try:
        from core.config import get_config

        config = get_config()

        minder_min = manifest.minder.get("min_version", "1.0.0")
        minder_max = manifest.minder.get("max_version", "999.0.0")

        # Simple version comparison (assumes standard semver)
        current_version = config.version
        if not (minder_min <= current_version <= minder_max):
            errors.append(
                f"Minder version mismatch: plugin requires {minder_min}-{minder_max}, current is {current_version}"
            )
    except Exception:
        # Skip version check if config is not available (e.g., in tests)
        pass

    # Check Python version
    import sys

    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    python_min = manifest.python.get("min_version", "3.11")
    python_max = manifest.python.get("max_version", "3.13")

    if not (python_min <= python_version <= python_max):
        errors.append(
            f"Python version mismatch: plugin requires {python_min}-{python_max}, current is {python_version}"
        )

    is_valid = len(errors) == 0
    return is_valid, manifest, errors
