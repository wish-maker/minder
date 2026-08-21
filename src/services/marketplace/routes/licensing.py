# services/marketplace/routes/licensing.py
import logging
from datetime import datetime, timezone

from core.licensing import create_license, get_user_licenses, validate_license
from core.validation import ensure_valid_plugin_id
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, field_validator

from shared.auth.jwt_middleware import get_current_user, require_role_or_service
from shared.errors import backend_http_error
from shared.models.tiers import normalize_tier

logger = logging.getLogger("minder.marketplace.licensing")

router = APIRouter(prefix="/v1/marketplace/licenses", tags=["Licensing"])


class LicenseValidateRequest(BaseModel):
    """Request model for license validation"""

    license_key: str
    plugin_id: str


class LicenseActivateRequest(BaseModel):
    """Request model for license activation.

    No user_id field -- identity comes from the JWT (`sub`), same as
    installations.py's install/uninstall (#147/C7). A caller-supplied user_id
    used to let any authenticated user activate (or silently overwrite) a
    license for ANY other account; there is still no payment/entitlement
    check behind this endpoint, so this closes the cross-account grant, not
    the "is self-service tier activation free" question (see the issue
    tracking that gap).
    """

    plugin_id: str
    # Canonical tier; "professional" accepted as a deprecated alias for "pro" (#142).
    tier: str

    @field_validator("tier")
    @classmethod
    def _normalize_tier(cls, v: str) -> str:
        return normalize_tier(v).value


@router.post("/validate")
async def validate_license_endpoint(
    request: LicenseValidateRequest, current_user: dict = Depends(get_current_user)
):
    """Validate a license key"""
    # plugin_id is queried against the UUID id column — reject a non-UUID here with
    # a clean 404 instead of letting asyncpg 500 (and leak the raw driver error,
    # since this handler has no try/except) (#574).
    ensure_valid_plugin_id(request.plugin_id)
    result = await validate_license(
        license_key=request.license_key, plugin_id=request.plugin_id
    )

    return result


@router.post("/activate")
async def activate_license(
    request: LicenseActivateRequest,
    current_user: dict = Depends(require_role_or_service("admin")),
):
    """Activate a license for the authenticated caller (identity from JWT, #147/C7).

    #622: gated to admin (or the internal service token) via
    ``require_role_or_service("admin")``. Before this, ANY authenticated user
    could self-mint an active license at ANY tier (community/pro/enterprise) for
    free — `create_license` performs no payment/entitlement check whatsoever, so
    a plain user could grant themselves enterprise. There is no payment processor
    anywhere in the codebase; until a real billing/entitlement model is decided
    (the open questions on #622), the contained fix is to stop unrestricted
    self-service tier activation by requiring admin — matching how model
    pull/delete and bundle enable/disable are gated elsewhere. A `role == "user"`
    JWT now gets 403; admins and the service principal are unaffected.
    """
    # Same UUID guard as validate (#574): a non-UUID plugin_id would otherwise hit
    # the UUID column and 500 (sanitized, via backend_http_error below) instead of a
    # clean 404.
    ensure_valid_plugin_id(request.plugin_id)
    user_id = current_user["sub"]
    try:
        license_data = await create_license(
            user_id=user_id, plugin_id=request.plugin_id, tier=request.tier
        )

        return {"status": "activated", "license": license_data}
    except Exception as e:
        logger.error(f"Failed to activate license for {user_id}: {e}")
        raise backend_http_error(e, "License activation")


@router.get("")
async def list_licenses(current_user: dict = Depends(get_current_user)):
    """Get all licenses for the authenticated user (identity from JWT).

    Previously took user_id as an unauthenticated query param -- any caller
    could read any other user's license records, including the plaintext
    license_key (the bearer secret validate_license accepts as proof of
    entitlement). Scoped to the caller's own JWT identity instead, matching
    installations.py's /me convention.
    """
    licenses = await get_user_licenses(current_user["sub"])

    return {"licenses": licenses, "count": len(licenses)}


@router.get("/lookup")
async def lookup_user_license(
    user_id: str = Query(...),
    plugin_id: str = Query(...),
    current_user: dict = Depends(require_role_or_service("admin")),
):
    """Service/admin-only: the tier of a SPECIFIC user's currently-active
    license for a SPECIFIC plugin, if any (#919).

    Used by plugin-state-manager's tool-tier enforcement to check a caller's
    real entitlement instead of the hardcoded "community" it used before this.
    Gated the same way ``activate_license`` above is -- a regular user must
    never be able to probe another user's license status by guessing their
    user_id, so this is admin/service only, not a plain JWT-any-user route.
    """
    ensure_valid_plugin_id(plugin_id)
    licenses = await get_user_licenses(user_id)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    match = next(
        (
            lic
            for lic in licenses
            if lic["plugin_id"] == plugin_id
            and lic["active"]
            and (
                lic["valid_until"] is None
                or datetime.fromisoformat(lic["valid_until"]) > now
            )
        ),
        None,
    )
    return {"tier": match["tier"] if match else None, "active": match is not None}
