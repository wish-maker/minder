# services/marketplace/routes/licensing.py
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from services.marketplace.core.licensing import (
    create_license,
    get_user_licenses,
    validate_license,
)
from shared.auth.jwt_middleware import get_current_user
from shared.models.tiers import normalize_tier

router = APIRouter(prefix="/v1/marketplace/licenses", tags=["Licensing"])


class LicenseValidateRequest(BaseModel):
    """Request model for license validation"""

    license_key: str
    plugin_id: str


class LicenseActivateRequest(BaseModel):
    """Request model for license activation"""

    user_id: str
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
    result = await validate_license(
        license_key=request.license_key, plugin_id=request.plugin_id
    )

    return result


@router.post("/activate")
async def activate_license(
    request: LicenseActivateRequest, current_user: dict = Depends(get_current_user)
):
    """Activate a license for a user and plugin"""
    try:
        license_data = await create_license(
            user_id=request.user_id, plugin_id=request.plugin_id, tier=request.tier
        )

        return {"status": "activated", "license": license_data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_licenses(user_id: str = Query(...)):
    """Get all licenses for a user"""
    licenses = await get_user_licenses(user_id)

    return {"licenses": licenses, "count": len(licenses)}
