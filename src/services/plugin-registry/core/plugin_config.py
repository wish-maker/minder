"""Central plugin configuration resolution (#34 UX / plugin management).

One place for the config → runtime-state path shared by the loader (on startup) and
the config API (on PUT). A plugin declares a ``CONFIG_SCHEMA`` (list of field
descriptors); the registry resolves each field default → env[key] → persisted
(API-set) value — persisted wins — coerces to the declared type, and calls the
plugin's ``apply_config(effective)`` so changes apply without a restart.
"""

import os
from typing import Any, Dict, List, Tuple

_TRUE = {"1", "true", "yes", "on"}


def _coerce(value: Any, typ: str) -> Any:
    """Coerce a value (often an env string) to the schema-declared type. Best effort."""
    if value is None:
        return None
    try:
        if typ == "int":
            return int(value)
        if typ == "float":
            return float(value)
        if typ == "bool":
            return value if isinstance(value, bool) else str(value).lower() in _TRUE
        return str(value)  # "string" / unknown
    except (TypeError, ValueError):
        return value


def get_schema(instance: Any) -> List[Dict[str, Any]]:
    schema = getattr(instance, "CONFIG_SCHEMA", None)
    return schema if isinstance(schema, list) else []


def effective_config(instance: Any, persisted: Dict[str, Any]) -> Dict[str, Any]:
    """Resolve each CONFIG_SCHEMA field: default → env[key] → persisted (persisted wins)."""
    out: Dict[str, Any] = {}
    for field in get_schema(instance):
        key, typ = field.get("key"), field.get("type", "string")
        if not key:
            continue
        val = field.get("default")
        if key in os.environ:
            val = os.environ[key]
        if key in persisted:
            val = persisted[key]
        out[key] = _coerce(val, typ)
    return out


def apply_effective(instance: Any, persisted: Dict[str, Any]) -> Dict[str, Any]:
    """Compute effective config and push it into the instance via apply_config().

    Returns the effective config. No-op (returns {}) for plugins without a schema.
    """
    if not get_schema(instance):
        return {}
    cfg = effective_config(instance, persisted)
    apply = getattr(instance, "apply_config", None)
    if callable(apply):
        apply(cfg)
    return cfg


def mask_secrets(instance: Any, values: Dict[str, Any]) -> Dict[str, Any]:
    """Redact fields marked secret in the schema, for safe GET output."""
    secret_keys = {f["key"] for f in get_schema(instance) if f.get("secret")}
    return {
        k: ("***" if (k in secret_keys and v not in (None, "")) else v)
        for k, v in values.items()
    }


def validate_update(instance: Any, incoming: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate a PUT body: must be a dict of KNOWN schema keys with coercible types."""
    if not isinstance(incoming, dict):
        return False, "body must be a JSON object of config keys"
    known = {f["key"]: f.get("type", "string") for f in get_schema(instance)}
    for key, val in incoming.items():
        if key not in known:
            return False, f"unknown config key '{key}'"
        typ = known[key]
        if typ in ("int", "float"):
            try:
                (int if typ == "int" else float)(val)
            except (TypeError, ValueError):
                return False, f"'{key}' must be {typ}"
    return True, ""
