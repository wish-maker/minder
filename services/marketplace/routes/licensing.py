# services/marketplace/routes/licensing.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.marketplace.core.licensing import create_license, get_user_licenses, validate_license

router = APIRouter(prefix="/v1/marketplace/licenses", tags=["Licensing"])


class LicenseValidateRequest(BaseModel):
    """Request model for license validation"""

    license_key: str
    plugin_id: str


class LicenseActivateRequest(BaseModel):
    """Request model for license activation"""

    user_id: str
    plugin_id: str
    tier: str


@router.post("/validate")
async def validate_license_endpoint(request: LicenseValidateRequest):
    """Validate a license key"""
    result = await validate_license(license_key=request.license_key, plugin_id=request.plugin_id)

    return result


@router.post("/activate")
async def activate_license(request: LicenseActivateRequest):
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
