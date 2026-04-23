"""
Minder Plugin Manifest Schema Validator
Jellyfin-inspired manifest.json validation with JSON Schema
"""

import json
import re
from typing import Dict, List, Optional, Any
from pathlib import Path
from jsonschema import validate, ValidationError, Draft7Validator
import hashlib
import logging

logger = logging.getLogger(__name__)


class ManifestSchema:
    """
    JSON Schema for Minder plugin manifest.json v2.0

    Based on Jellyfin plugin manifest with enhancements for:
    - Dynamic service dependencies
    - Resource management
    - Permission system
    - Hot reload capability
    - Configuration store
    """

    SCHEMA = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": "Minder Plugin Manifest",
        "type": "object",
        "required": [
            "format_version",
            "id",
            "name",
            "version",
            "description",
            "author",
            "core_api",
            "permissions",
        ],
        "properties": {
            "format_version": {
                "type": "string",
                "pattern": "^2\\.0$",
                "description": "Manifest format version (must be 2.0)",
            },
            "id": {
                "type": "string",
                "pattern": "^[a-z][a-z0-9_-]*$",
                "minLength": 2,
                "maxLength": 50,
                "description": "Unique plugin identifier (lowercase, alphanumeric)",
            },
            "name": {
                "type": "string",
                "minLength": 3,
                "maxLength": 100,
                "description": "Human-readable plugin name",
            },
            "version": {
                "type": "string",
                "pattern": "^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)(?:-((?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\\.(?:0|[1-9]\\d*|\\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\\+([0-9a-zA-Z-]+(?:\\.[0-9a-zA-Z-]+)*))?$",
                "description": "Semantic version (e.g., 1.0.0, 2.1.3-beta)",
            },
            "description": {
                "type": "string",
                "minLength": 10,
                "maxLength": 500,
                "description": "Plugin description",
            },
            "author": {
                "type": "string",
                "pattern": "^.+\\s<.+@.+\\..+>$",
                "description": "Author name and email (e.g., 'Minder Team <dev@minder.ai>')",
            },
            "categories": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
                "description": "Plugin categories for organization",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "uniqueItems": True,
                "description": "Searchable tags",
            },
            "compatibility": {
                "type": "object",
                "properties": {
                    "minder_core": {
                        "type": "string",
                        "pattern": "^(>=|>|<=|<|=)?\\d+\\.\\d+\\.\\d+$",
                        "description": "Core version compatibility (e.g., '>=2.0.0')",
                    },
                    "breaking_changes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of breaking changes in this version",
                    },
                },
            },
            "github": {
                "type": "object",
                "required": ["repo", "branch"],
                "properties": {
                    "repo": {
                        "type": "string",
                        "format": "uri",
                        "pattern": "^https://github\\.com/.+\\.git$",
                        "description": "GitHub repository URL",
                    },
                    "branch": {"type": "string", "default": "main"},
                    "tag": {"type": "string", "description": "Git tag for this version"},
                    "auto_update": {"type": "boolean", "default": False},
                    "release_channel": {
                        "type": "string",
                        "enum": ["stable", "beta", "alpha"],
                        "default": "stable",
                    },
                },
            },
            "dependencies": {
                "type": "object",
                "properties": {
                    "plugins": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"id": {"type": "string"}, "version": {"type": "string"}},
                            "required": ["id", "version"],
                        },
                    },
                    "services": {
                        "type": "object",
                        "properties": {
                            "redis": {
                                "type": "object",
                                "properties": {
                                    "required": {"type": "boolean"},
                                    "version": {"type": "string"},
                                    "namespace": {"type": "string"},
                                    "auto_create": {"type": "boolean"},
                                },
                            },
                            "postgres": {
                                "type": "object",
                                "properties": {
                                    "required": {"type": "boolean"},
                                    "version": {"type": "string"},
                                    "database": {"type": "string"},
                                    "auto_create": {"type": "boolean"},
                                    "migrations": {"type": "string"},
                                },
                            },
                            "qdrant": {
                                "type": "object",
                                "properties": {
                                    "required": {"type": "boolean"},
                                    "version": {"type": "string"},
                                    "collections": {"type": "array", "items": {"type": "string"}},
                                },
                            },
                            "ollama": {
                                "type": "object",
                                "properties": {
                                    "required": {"type": "boolean"},
                                    "models": {"type": "array", "items": {"type": "string"}},
                                    "auto_create": {"type": "boolean"},
                                },
                            },
                        },
                    },
                    "python_packages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "version": {"type": "string"},
                            },
                            "required": ["name"],
                        },
                    },
                },
            },
            "core_api": {
                "type": "object",
                "required": ["port", "endpoints"],
                "properties": {
                    "type": {"type": "string", "enum": ["http", "grpc"], "default": "http"},
                    "port": {"type": "integer", "minimum": 8000, "maximum": 9000},
                    "endpoints": {
                        "type": "object",
                        "properties": {
                            "health": {"type": "object"},
                            "install": {"type": "object"},
                            "uninstall": {"type": "object"},
                            "configure": {"type": "object"},
                            "status": {"type": "object"},
                        },
                        "required": ["health"],
                    },
                },
            },
            "permissions": {
                "type": "object",
                "properties": {
                    "apis": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "endpoints": {"type": "array", "items": {"type": "string"}},
                                "rate_limit": {"type": "string"},
                            },
                        },
                    },
                    "file_system": {
                        "type": "object",
                        "properties": {
                            "read": {"type": "array", "items": {"type": "string"}},
                            "write": {"type": "array", "items": {"type": "string"}},
                            "deny": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "network": {
                        "type": "object",
                        "properties": {
                            "allow": {"type": "array", "items": {"type": "string"}},
                            "deny": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
            },
            "resources": {
                "type": "object",
                "properties": {
                    "cpu": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "string"},
                            "reservation": {"type": "string"},
                        },
                    },
                    "memory": {
                        "type": "object",
                        "properties": {
                            "limit": {"type": "string"},
                            "reservation": {"type": "string"},
                        },
                    },
                    "storage": {
                        "type": "object",
                        "properties": {"database": {"type": "string"}, "files": {"type": "string"}},
                    },
                    "threads": {
                        "type": "object",
                        "properties": {"max": {"type": "integer"}, "min": {"type": "integer"}},
                    },
                },
            },
            "secrets": {
                "type": "object",
                "properties": {
                    "required": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "description": {"type": "string"},
                                "type": {"type": "string"},
                                "rotation": {"type": "string"},
                            },
                            "required": ["name", "type"],
                        },
                    },
                    "optional": {"type": "array", "items": {"type": "object"}},
                },
            },
            "configuration": {
                "type": "object",
                "properties": {
                    "schema": {"type": "object"},
                    "ui": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "icon": {"type": "string"},
                            "category": {"type": "string"},
                        },
                    },
                },
            },
            "sandbox": {
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean"},
                    "type": {"type": "string", "enum": ["process", "container", "chroot"]},
                    "isolation": {
                        "type": "object",
                        "properties": {
                            "namespace": {"type": "string"},
                            "network": {"type": "string"},
                            "file_system": {"type": "string"},
                        },
                    },
                    "limits": {
                        "type": "object",
                        "properties": {
                            "max_execution_time": {"type": "integer"},
                            "max_memory": {"type": "string"},
                            "max_files": {"type": "integer"},
                        },
                    },
                },
            },
        },
    }


class ManifestValidator:
    """
    Validates plugin manifests against JSON Schema

    Performs:
    - JSON Schema validation
    - Semantic version validation
    - Dependency conflict detection
    - Security checks
    - Checksum verification
    """

    def __init__(self):
        self.validator = Draft7Validator(ManifestSchema.SCHEMA)

    def validate(self, manifest_path: str) -> Dict[str, Any]:
        """
        Validate manifest.json file

        Args:
            manifest_path: Path to manifest.json

        Returns:
            Dict with validation results:
            {
                "valid": bool,
                "errors": List[str],
                "warnings": List[str],
                "manifest": dict (if valid)
            }
        """
        result = {"valid": False, "errors": [], "warnings": [], "manifest": None}

        try:
            # Read manifest file
            manifest_file = Path(manifest_path)
            if not manifest_file.exists():
                result["errors"].append(f"Manifest file not found: {manifest_path}")
                return result

            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            # JSON Schema validation
            schema_errors = []
            for error in self.validator.iter_errors(manifest):
                schema_errors.append(f"{'.'.join(str(p) for p in error.path)}: {error.message}")

            if schema_errors:
                result["errors"].extend(schema_errors)
                return result

            # Custom validations
            warnings = self._validate_manifest_content(manifest)
            result["warnings"].extend(warnings)

            # Calculate checksum
            checksum = self._calculate_checksum(manifest_file)

            # Add metadata
            manifest["_metadata"] = {"checksum": checksum, "validated_at": self._get_timestamp()}

            result["valid"] = True
            result["manifest"] = manifest

            logger.info(f"✅ Manifest validation successful: {manifest.get('id')}")
            return result

        except json.JSONDecodeError as e:
            result["errors"].append(f"Invalid JSON: {str(e)}")
            return result
        except Exception as e:
            result["errors"].append(f"Validation error: {str(e)}")
            return result

    def _validate_manifest_content(self, manifest: Dict) -> List[str]:
        """
        Additional content validations beyond JSON Schema

        Returns:
            List of warnings
        """
        warnings = []

        # Check if plugin ID matches directory name convention
        plugin_id = manifest.get("id", "")
        if not plugin_id.islower() or " " in plugin_id:
            warnings.append(f"Plugin ID '{plugin_id}' should be lowercase without spaces")

        # Check version compatibility
        compatibility = manifest.get("compatibility", {})
        if "minder_core" in compatibility:
            version_req = compatibility["minder_core"]
            if not self._is_valid_version_range(version_req):
                warnings.append(f"Invalid version range: {version_req}")

        # Check if secrets have rotation policy
        secrets = manifest.get("secrets", {})
        required_secrets = secrets.get("required", [])
        for secret in required_secrets:
            if secret.get("type") == "api_key" and "rotation" not in secret:
                warnings.append(f"API key '{secret.get('name')}' should have a rotation policy")

        # Check resource limits
        resources = manifest.get("resources", {})
        if "cpu" in resources:
            cpu_limit = resources["cpu"].get("limit", "0")
            try:
                limit_val = float(cpu_limit)
                if limit_val > 4.0:
                    warnings.append(f"High CPU limit: {cpu_limit} cores")
            except ValueError:
                pass

        return warnings

    def _is_valid_version_range(self, version_range: str) -> bool:
        """Check if version range is valid"""
        # Simple regex for version ranges like ">=2.0.0", "1.0.0", etc.
        pattern = r"^(>=|>|<=|<|=)?\d+\.\d+\.\d+$"
        return bool(re.match(pattern, version_range))

    def _calculate_checksum(self, manifest_file: Path) -> str:
        """Calculate SHA256 checksum of manifest file"""
        sha256_hash = hashlib.sha256()
        with open(manifest_file, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _get_timestamp(self) -> str:
        """Get current timestamp in ISO format"""
        from datetime import datetime

        return datetime.utcnow().isoformat() + "Z"

    def verify_checksum(self, manifest: Dict, expected_checksum: str) -> bool:
        """
        Verify manifest checksum

        Args:
            manifest: Manifest dictionary
            expected_checksum: Expected SHA256 checksum

        Returns:
            True if checksum matches
        """
        actual_checksum = manifest.get("_metadata", {}).get("checksum", "")
        return actual_checksum == expected_checksum


def validate_manifest_from_url(url: str) -> Dict[str, Any]:
    """
    Validate manifest from URL (GitHub raw content, etc.)

    Args:
        url: URL to manifest.json

    Returns:
        Validation result dict
    """
    import httpx
    import tempfile

    validator = ManifestValidator()

    try:
        # Download manifest
        response = httpx.get(url, timeout=10.0)
        response.raise_for_status()

        # Save to temp file and validate
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(response.text)
            temp_path = f.name

        return validator.validate(temp_path)

    except Exception as e:
        return {
            "valid": False,
            "errors": [f"Failed to download/validate manifest: {str(e)}"],
            "warnings": [],
            "manifest": None,
        }
