"""Unit tests for marketplace licensing routes' identity-from-JWT scoping.

Two real bugs found in a background audit pass: GET /v1/marketplace/licenses took
an unauthenticated `user_id` query param -- any caller could read any other user's
license records, including the plaintext license_key (the bearer secret
validate_license accepts as proof of entitlement). POST .../activate took a
client-supplied `user_id` in the body with only "some authenticated user" as the
gate -- any logged-in user could activate (or silently overwrite) a license for
ANY other account. Both now derive user_id from the JWT (`current_user["sub"]`)
instead, matching installations.py's existing /me convention (#147/C7).

Isolated-import pattern matches test_marketplace_my_installations.py.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_SERVICE_DIR = Path(__file__).resolve().parents[2] / "src" / "services" / "marketplace"
_COLLISION_PRONE_NAMES = ("core", "routes", "models", "config")


def _isolated_import(*module_paths: str):
    saved_path = list(sys.path)
    saved_modules = {}
    for name in _COLLISION_PRONE_NAMES:
        for key in list(sys.modules):
            if key == name or key.startswith(name + "."):
                saved_modules[key] = sys.modules.pop(key)
    sys.path.insert(0, str(_SERVICE_DIR))
    import os

    os.environ.setdefault("DB_PASSWORD", "test")
    os.environ.setdefault("REDIS_PASSWORD", "test")
    os.environ.setdefault("JWT_SECRET", "test")
    os.environ.setdefault("NEO4J_AUTH", "neo4j/test")

    import importlib

    try:
        return [importlib.import_module(p) for p in module_paths]
    finally:
        sys.path[:] = saved_path
        for name in _COLLISION_PRONE_NAMES:
            for key in list(sys.modules):
                if key == name or key.startswith(name + "."):
                    sys.modules.pop(key, None)
        sys.modules.update(saved_modules)


(licensing_routes,) = _isolated_import("routes.licensing")


@pytest.mark.asyncio
async def test_list_licenses_scopes_to_jwt_identity_not_a_query_param(monkeypatch):
    """No more `user_id` query param -- the route signature itself no longer
    accepts one, so there is nothing for a caller to override."""
    get_user_licenses = AsyncMock(return_value=[{"id": "lic-1"}])
    monkeypatch.setattr(licensing_routes, "get_user_licenses", get_user_licenses)

    result = await licensing_routes.list_licenses(current_user={"sub": "victim-user"})

    get_user_licenses.assert_awaited_once_with("victim-user")
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_activate_license_uses_jwt_identity_not_request_body(monkeypatch):
    """LicenseActivateRequest no longer has a user_id field at all -- a request
    can no longer name a different account to activate a license for."""
    create_license = AsyncMock(return_value={"id": "lic-1", "active": True})
    monkeypatch.setattr(licensing_routes, "create_license", create_license)
    monkeypatch.setattr(licensing_routes, "ensure_valid_plugin_id", lambda pid: None)

    request = licensing_routes.LicenseActivateRequest(
        plugin_id="11111111-1111-1111-1111-111111111111", tier="pro"
    )
    assert not hasattr(request, "user_id")

    result = await licensing_routes.activate_license(
        request, current_user={"sub": "caller-user"}
    )

    create_license.assert_awaited_once_with(
        user_id="caller-user",
        plugin_id="11111111-1111-1111-1111-111111111111",
        tier="pro",
    )
    assert result["status"] == "activated"
