"""Shared request-validation helpers for marketplace routes."""

import uuid

from fastapi import HTTPException


def ensure_valid_plugin_id(plugin_id: str) -> str:
    """Reject a non-UUID ``plugin_id`` with a clean 404 instead of passing it
    through to a query against the UUID ``id`` column, where asyncpg raises and
    the request 500s leaking the raw driver error (#526). A malformed id can't
    match any plugin, so 404 "Plugin not found" mirrors the valid-but-absent case.

    Call this directly when the id arrives in the request BODY (e.g. the licensing
    endpoints, #574); use ``valid_plugin_id`` as a Depends for ``{plugin_id}`` path
    params.
    """
    try:
        uuid.UUID(plugin_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Plugin not found")
    return plugin_id


def valid_plugin_id(plugin_id: str) -> str:
    """FastAPI dependency form of :func:`ensure_valid_plugin_id` for ``{plugin_id}``
    path routes. Use as ``plugin_id: str = Depends(valid_plugin_id)``."""
    return ensure_valid_plugin_id(plugin_id)
