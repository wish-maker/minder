"""Shared request-validation helpers for marketplace routes."""

import uuid

from fastapi import HTTPException


def valid_plugin_id(plugin_id: str) -> str:
    """FastAPI dependency: reject a non-UUID ``plugin_id`` with a clean 404
    instead of passing it through to a query against the UUID ``id`` column,
    where asyncpg raises and the request 500s leaking the raw driver error
    (#526). A malformed id can't match any plugin, so 404 "Plugin not found"
    mirrors the valid-but-absent case. Use as
    ``plugin_id: str = Depends(valid_plugin_id)`` on every ``{plugin_id}`` route.
    """
    try:
        uuid.UUID(plugin_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin_id
