"""
Minder Configuration Store
Central configuration management with schema validation and versioning
"""

import logging
import json
from typing import Dict, Optional, Any, List
from datetime import datetime
from pathlib import Path
import jsonschema
from jsonschema import validate, ValidationError
import hashlib

logger = logging.getLogger(__name__)


class ConfigurationStore:
    """
    Central configuration management for plugins

    Features:
    - Schema validation
    - Version tracking
    - Rollback support
    - Configuration history
    """

    def __init__(self, config_path: str = "/var/lib/minder/config"):
        self.config_path = Path(config_path)
        self.config_path.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self.configs: Dict[str, Dict] = {}  # {plugin_id: config}
        self.config_versions: Dict[str, List[Dict]] = {}  # {plugin_id: [versions]}

        self.logger = logging.getLogger(__name__)

    async def get_plugin_config(self, plugin_id: str) -> Dict:
        """
        Get current plugin configuration

        Args:
            plugin_id: Plugin identifier

        Returns:
            Configuration dict
        """
        try:
            # Check cache first
            if plugin_id in self.configs:
                return self.configs[plugin_id]

            # Load from file
            config_file = self.config_path / f"{plugin_id}.json"
            if config_file.exists():
                with open(config_file, "r") as f:
                    config = json.load(f)
                    self.configs[plugin_id] = config
                    return config
            else:
                # Return empty config
                return {}

        except Exception as e:
            self.logger.error(f"❌ Failed to load config for {plugin_id}: {e}")
            return {}

    async def update_plugin_config(
        self, plugin_id: str, config: Dict, schema: Dict = None, create_version: bool = True
    ) -> Dict:
        """
        Update plugin configuration

        Args:
            plugin_id: Plugin identifier
            config: New configuration
            schema: JSON schema for validation
            create_version: Create version snapshot

        Returns:
            Result dict
        """
        result = {"success": False, "version": None, "errors": []}

        try:
            # Validate against schema if provided
            if schema:
                validation = await self.validate_config(plugin_id, config, schema)
                if not validation["valid"]:
                    result["errors"] = validation["errors"]
                    return result

            # Create version snapshot of current config
            if create_version and plugin_id in self.configs:
                await self._create_version_snapshot(plugin_id, self.configs[plugin_id])

            # Update config
            self.configs[plugin_id] = config

            # Calculate version
            version = await self._get_next_version(plugin_id)

            # Add metadata
            config_with_meta = {
                "config": config,
                "metadata": {
                    "plugin_id": plugin_id,
                    "version": version,
                    "updated_at": datetime.utcnow().isoformat(),
                    "checksum": self._calculate_checksum(config),
                },
            }

            # Save to file
            config_file = self.config_path / f"{plugin_id}.json"
            with open(config_file, "w") as f:
                json.dump(config_with_meta, f, indent=2)

            result["success"] = True
            result["version"] = version

            self.logger.info(f"✅ Updated config for {plugin_id} (v{version})")

            return result

        except Exception as e:
            self.logger.error(f"❌ Failed to update config for {plugin_id}: {e}")
            result["errors"].append(str(e))
            return result

    async def validate_config(self, plugin_id: str, config: Dict, schema: Dict) -> Dict:
        """
        Validate configuration against schema

        Args:
            plugin_id: Plugin identifier
            config: Configuration to validate
            schema: JSON schema

        Returns:
            Validation result dict
        """
        result = {"valid": False, "errors": []}

        try:
            # Validate against schema
            validate(instance=config, schema=schema)
            result["valid"] = True
            self.logger.info(f"✅ Config validation passed for {plugin_id}")

        except ValidationError as e:
            result["valid"] = False
            result["errors"] = [e.message]
            self.logger.warning(f"⚠️ Config validation failed for {plugin_id}: {e.message}")

        except Exception as e:
            result["valid"] = False
            result["errors"] = [str(e)]
            self.logger.error(f"❌ Validation error for {plugin_id}: {e}")

        return result

    async def get_config_history(self, plugin_id: str) -> List[Dict]:
        """
        Get configuration history for plugin

        Args:
            plugin_id: Plugin identifier

        Returns:
            List of version dicts
        """
        if plugin_id not in self.config_versions:
            return []

        return self.config_versions[plugin_id]

    async def get_config_version(self, plugin_id: str, version: str) -> Optional[Dict]:
        """
        Get specific version of configuration

        Args:
            plugin_id: Plugin identifier
            version: Version number

        Returns:
            Configuration dict or None
        """
        versions = await self.get_config_history(plugin_id)

        for v in versions:
            if v["version"] == version:
                return v["config"]

        return None

    async def rollback_config(self, plugin_id: str, target_version: str) -> Dict:
        """
        Rollback configuration to previous version

        Args:
            plugin_id: Plugin identifier
            target_version: Target version to rollback to

        Returns:
            Result dict
        """
        result = {"success": False, "from_version": None, "to_version": target_version, "errors": []}

        try:
            # Get current version
            current_config = await self.get_plugin_config(plugin_id)
            if not current_config:
                result["errors"].append("No current configuration found")
                return result

            from_version = current_config.get("metadata", {}).get("version", "unknown")
            result["from_version"] = from_version

            # Get target version
            target_config = await self.get_config_version(plugin_id, target_version)
            if not target_config:
                result["errors"].append(f"Version {target_version} not found")
                return result

            # Create version snapshot before rollback
            await self._create_version_snapshot(plugin_id, current_config)

            # Rollback to target version
            update_result = await self.update_plugin_config(
                plugin_id=plugin_id, config=target_config, create_version=False  # Don't create version of rollback
            )

            if update_result["success"]:
                result["success"] = True
                self.logger.info(f"✅ Rolled back {plugin_id} config from v{from_version} to v{target_version}")
            else:
                result["errors"].extend(update_result.get("errors", []))

            return result

        except Exception as e:
            self.logger.error(f"❌ Rollback failed for {plugin_id}: {e}")
            result["errors"].append(str(e))
            return result

    async def delete_plugin_config(self, plugin_id: str) -> bool:
        """
        Delete plugin configuration

        Args:
            plugin_id: Plugin identifier

        Returns:
            True if successful
        """
        try:
            # Remove from cache
            if plugin_id in self.configs:
                del self.configs[plugin_id]

            # Remove from versions
            if plugin_id in self.config_versions:
                del self.config_versions[plugin_id]

            # Remove file
            config_file = self.config_path / f"{plugin_id}.json"
            if config_file.exists():
                config_file.unlink()

            self.logger.info(f"🗑️ Deleted config for {plugin_id}")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to delete config for {plugin_id}: {e}")
            return False

    async def _create_version_snapshot(self, plugin_id: str, config: Dict):
        """Create version snapshot of configuration"""
        if plugin_id not in self.config_versions:
            self.config_versions[plugin_id] = []

        version = config.get("metadata", {}).get("version", "1")

        snapshot = {"version": version, "config": config.copy(), "created_at": datetime.utcnow().isoformat()}

        self.config_versions[plugin_id].append(snapshot)

        # Keep only last 100 versions
        if len(self.config_versions[plugin_id]) > 100:
            self.config_versions[plugin_id] = self.config_versions[plugin_id][-100:]

    async def _get_next_version(self, plugin_id: str) -> str:
        """Get next version number for plugin config"""
        if plugin_id not in self.config_versions:
            return "1"

        versions = self.config_versions[plugin_id]
        if not versions:
            return "1"

        # Extract max version number
        max_version = 0
        for v in versions:
            try:
                version_num = int(v["version"])
                if version_num > max_version:
                    max_version = version_num
            except:
                pass

        return str(max_version + 1)

    def _calculate_checksum(self, config: Dict) -> str:
        """Calculate SHA256 checksum of config"""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()

    async def export_config(self, plugin_id: str) -> Optional[str]:
        """
        Export configuration as JSON string

        Args:
            plugin_id: Plugin identifier

        Returns:
            JSON string or None
        """
        try:
            config = await self.get_plugin_config(plugin_id)
            if config:
                return json.dumps(config, indent=2)
            return None
        except Exception as e:
            self.logger.error(f"❌ Failed to export config: {e}")
            return None

    async def import_config(self, plugin_id: str, config_json: str, schema: Dict = None) -> Dict:
        """
        Import configuration from JSON string

        Args:
            plugin_id: Plugin identifier
            config_json: JSON string
            schema: Optional JSON schema

        Returns:
            Result dict
        """
        try:
            config = json.loads(config_json)
            return await self.update_plugin_config(plugin_id=plugin_id, config=config, schema=schema)
        except Exception as e:
            self.logger.error(f"❌ Failed to import config: {e}")
            return {"success": False, "errors": [str(e)]}

    async def get_all_configs(self) -> Dict[str, Dict]:
        """
        Get all plugin configurations

        Returns:
            Dict of plugin_id: config
        """
        configs = {}

        # Load all config files
        for config_file in self.config_path.glob("*.json"):
            plugin_id = config_file.stem
            try:
                with open(config_file, "r") as f:
                    config = json.load(f)
                    configs[plugin_id] = config
            except Exception as e:
                self.logger.error(f"❌ Failed to load config from {config_file}: {e}")

        return configs

    async def merge_config(self, plugin_id: str, updates: Dict, schema: Dict = None) -> Dict:
        """
        Merge updates into existing configuration

        Args:
            plugin_id: Plugin identifier
            updates: Dict with updates to merge
            schema: Optional JSON schema

        Returns:
            Result dict
        """
        try:
            # Get current config
            current = await self.get_plugin_config(plugin_id)

            # Deep merge
            merged = self._deep_merge(current, updates)

            # Update
            return await self.update_plugin_config(plugin_id=plugin_id, config=merged, schema=schema)

        except Exception as e:
            self.logger.error(f"❌ Failed to merge config: {e}")
            return {"success": False, "errors": [str(e)]}

    def _deep_merge(self, base: Dict, updates: Dict) -> Dict:
        """Deep merge two dicts"""
        result = base.copy()

        for key, value in updates.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    async def get_diff(self, plugin_id: str, version1: str = None, version2: str = None) -> Dict:
        """
        Get diff between two configuration versions

        Args:
            plugin_id: Plugin identifier
            version1: First version (None = current)
            version2: Second version (None = previous)

        Returns:
            Diff dict
        """
        try:
            # Get configs
            config1 = (
                await self.get_plugin_config(plugin_id)
                if version1 is None
                else await self.get_config_version(plugin_id, version1)
            )

            if version2 is None:
                # Get previous version
                versions = await self.get_config_history(plugin_id)
                if len(versions) >= 2:
                    config2 = versions[-2]["config"]
                else:
                    config2 = {}
            else:
                config2 = await self.get_config_version(plugin_id, version2)

            # Calculate diff
            diff = self._calculate_diff(config1, config2)

            return {
                "plugin_id": plugin_id,
                "version1": version1 or "current",
                "version2": version2 or "previous",
                "diff": diff,
            }

        except Exception as e:
            self.logger.error(f"❌ Failed to calculate diff: {e}")
            return {"plugin_id": plugin_id, "diff": {}, "error": str(e)}

    def _calculate_diff(self, config1: Dict, config2: Dict) -> Dict:
        """Calculate diff between two configs"""
        diff = {"added": {}, "removed": {}, "changed": {}}

        # Check for added and changed keys
        for key, value in config1.items():
            if key not in config2:
                diff["added"][key] = value
            elif config2[key] != value:
                diff["changed"][key] = {"old": config2[key], "new": value}

        # Check for removed keys
        for key in config2:
            if key not in config1:
                diff["removed"][key] = config2[key]

        return diff
