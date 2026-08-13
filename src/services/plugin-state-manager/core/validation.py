"""Shared request-validation helpers for plugin-state-manager routes."""

import uuid

from fastapi import HTTPException


def ensure_valid_plugin_id(plugin_id: str) -> str:
    """Reject a non-UUID ``plugin_id`` with a clean 404 instead of passing it
    through to a query against the marketplace DB's UUID ``id`` column, where
    asyncpg raises and the request 500s (#576 — the same class as marketplace #574
    /#526). A malformed id can't match any plugin, so 404 "Plugin not found"
    mirrors the valid-but-absent case.
    """
    try:
        uuid.UUID(plugin_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin_id
