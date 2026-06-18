"""
Manifest Validator

Validates MVP plugin manifests against schema.
NO code execution - only parameter validation.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

import yaml
from jsonschema import validate, ValidationError
from schemas.mvp_manifest import MVP_MANIFEST_SCHEMA

logger = logging.getLogger(__name__)


class ManifestValidationError(Exception):
    """Raised when manifest validation fails"""
    def __init__(self, errors: list):
        self.errors = errors
        super().__init__(f"Manifest validation failed: {len(errors)} error(s)")


def validate_manifest(manifest_data: Dict) -> Tuple[bool, Optional[list]]:
    """
    Validate manifest against MVP schema.

    Args:
        manifest_data: Parsed manifest (dict)

    Returns:
        (is_valid, errors) - errors is None if valid, list of error strings if invalid

    SECURITY NOTE: This only validates structure and types.
    NO code execution, NO eval(), NO dynamic imports.
    """
    errors = []

    try:
        validate(instance=manifest_data, schema=MVP_MANIFEST_SCHEMA)
    except ValidationError as e:
        errors.append({
            "path": " -> ".join(str(p) for p in e.path) if e.path else "root",
            "message": e.message,
            "failed_value": e.instance
        })

    # Additional security checks
    if manifest_data.get("apiVersion") != "minder.dev/v1alpha1":
        errors.append({"path": "apiVersion", "message": "Only v1alpha1 supported in MVP"})

    if manifest_data.get("kind") != "Plugin":
        errors.append({"path": "kind", "message": "Only Plugin kind supported"})

    # Ensure trigger type is webhook (MVP only)
    trigger = manifest_data.get("spec", {}).get("trigger", {})
    if trigger.get("type") != "webhook":
        errors.append({"path": "spec.trigger.type", "message": "Only webhook trigger supported in MVP"})

    # Ensure action type is store-vector (MVP only)
    action = manifest_data.get("spec", {}).get("action", {})
    if action.get("type") != "store-vector":
        errors.append({"path": "spec.action.type", "message": "Only store-vector action supported in MVP"})

    # Check webhook path is valid
    webhook_config = trigger.get("webhook", {})
    webhook_path = webhook_config.get("path", "")
    if not webhook_path.startswith("/"):
        errors.append({"path": "spec.trigger.webhook.path", "message": "Path must start with /"})

    # Check collection name is valid
    store_config = action.get("store", {})
    collection = store_config.get("collection", "")
    if not collection:
        errors.append({"path": "spec.action.store.collection", "message": "Collection name required"})

    # Check input.text template exists
    input_config = store_config.get("input", {})
    text_template = input_config.get("text", "")
    if not text_template:
        errors.append({"path": "spec.action.store.input.text", "message": "Text template required"})

    is_valid = len(errors) == 0
    return (is_valid, None if is_valid else errors)


def load_and_validate_manifest(manifest_path: Path) -> Tuple[Optional[Dict], Optional[list]]:
    """
    Load manifest from file and validate it.

    Args:
        manifest_path: Path to manifest.yml or manifest.json

    Returns:
        (manifest_data, errors) - manifest_data is None if invalid
    """
    if not manifest_path.exists():
        return None, [{"path": "file", "message": f"File not found: {manifest_path}"}]

    try:
        with open(manifest_path, 'r') as f:
            if manifest_path.suffix in ['.yaml', '.yml']:
                manifest_data = yaml.safe_load(f)
            elif manifest_path.suffix == '.json':
                manifest_data = json.load(f)
            else:
                return None, [{"path": "file", "message": f"Unsupported file type: {manifest_path.suffix}"}]

        is_valid, errors = validate_manifest(manifest_data)

        if not is_valid:
            return None, errors

        return manifest_data, None

    except yaml.YAMLError as e:
        return None, [{"path": "file", "message": f"YAML parsing error: {e}"}]
    except json.JSONDecodeError as e:
        return None, [{"path": "file", "message": f"JSON parsing error: {e}"}]
    except Exception as e:
        return None, [{"path": "file", "message": f"Error reading file: {e}"}]


def validate_manifest_string(manifest_yaml: str) -> Tuple[Optional[Dict], Optional[list]]:
    """
    Validate manifest from string (for API upload).

    Args:
        manifest_yaml: YAML string

    Returns:
        (manifest_data, errors) - manifest_data is None if invalid
    """
    try:
        manifest_data = yaml.safe_load(manifest_yaml)
        is_valid, errors = validate_manifest(manifest_data)

        if not is_valid:
            return None, errors

        return manifest_data, None

    except yaml.YAMLError as e:
        return None, [{"path": "content", "message": f"YAML parsing error: {e}"}]
    except Exception as e:
        return None, [{"path": "content", "message": f"Error parsing: {e}"}]
