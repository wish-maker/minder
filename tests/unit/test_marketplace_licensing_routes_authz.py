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


# ── validate_license_endpoint: entirely untested before this file ────────────


@pytest.mark.asyncio
async def test_validate_license_endpoint_returns_validation_result(monkeypatch):
    validate_license = AsyncMock(return_value={"valid": True, "tier": "pro"})
    monkeypatch.setattr(licensing_routes, "validate_license", validate_license)
    monkeypatch.setattr(licensing_routes, "ensure_valid_plugin_id", lambda pid: None)

    request = licensing_routes.LicenseValidateRequest(
        license_key="key-123", plugin_id="11111111-1111-1111-1111-111111111111"
    )

    result = await licensing_routes.validate_license_endpoint(
        request, current_user={"sub": "caller-user"}
    )

    validate_license.assert_awaited_once_with(
        license_key="key-123", plugin_id="11111111-1111-1111-1111-111111111111"
    )
    assert result == {"valid": True, "tier": "pro"}


@pytest.mark.asyncio
async def test_validate_license_endpoint_rejects_a_non_uuid_plugin_id(monkeypatch):
    from fastapi import HTTPException

    def fake_guard(pid):
        raise HTTPException(status_code=404, detail="Plugin not found")

    monkeypatch.setattr(licensing_routes, "ensure_valid_plugin_id", fake_guard)
    request = licensing_routes.LicenseValidateRequest(
        license_key="key-123", plugin_id="not-a-uuid"
    )

    with pytest.raises(HTTPException) as exc_info:
        await licensing_routes.validate_license_endpoint(
            request, current_user={"sub": "caller-user"}
        )

    assert exc_info.value.status_code == 404


# ── activate_license: exception branch ────────────────────────────────────────


# ── #622: activate is admin-gated (no unrestricted self-service tier grant) ───


def _activate_route_dependency():
    """The dependency callable FastAPI resolves for POST /activate — i.e. the
    require_role_or_service('admin') gate the route is now wired with (#622)."""
    route = next(
        r
        for r in licensing_routes.router.routes
        if getattr(r, "path", "").endswith("/activate")
        and "POST" in (getattr(r, "methods", None) or set())
    )
    # A single Depends on the endpoint's `current_user` param.
    return route.dependant.dependencies[0].call


@pytest.mark.asyncio
async def test_activate_gate_rejects_a_plain_user(monkeypatch):
    """A role='user' JWT can no longer self-activate a license (was: any tier,
    free). The gate raises 403 before the handler runs (#622)."""
    from fastapi import HTTPException

    gate = _activate_route_dependency()
    with pytest.raises(HTTPException) as exc:
        await gate(user={"sub": "normal-user", "role": "user"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_activate_gate_allows_admin_and_service(monkeypatch):
    gate = _activate_route_dependency()
    admin = await gate(user={"sub": "an-admin", "role": "admin"})
    assert admin["sub"] == "an-admin"
    # The internal service token is accepted unconditionally (matches the
    # require_role_or_service model used elsewhere).
    svc = await gate(user={"sub": "internal-service", "role": "service"})
    assert svc["role"] == "service"


@pytest.mark.asyncio
async def test_activate_license_maps_backend_error(monkeypatch):
    create_license = AsyncMock(side_effect=RuntimeError("db unreachable"))
    monkeypatch.setattr(licensing_routes, "create_license", create_license)
    monkeypatch.setattr(licensing_routes, "ensure_valid_plugin_id", lambda pid: None)

    request = licensing_routes.LicenseActivateRequest(
        plugin_id="11111111-1111-1111-1111-111111111111", tier="pro"
    )

    with pytest.raises(Exception) as exc_info:
        await licensing_routes.activate_license(
            request, current_user={"sub": "caller-user"}
        )

    assert exc_info.value.status_code == 500
    assert "db unreachable" not in str(exc_info.value.detail)
