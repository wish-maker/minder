# services/plugin-state-manager/routes/licensing.py
"""
Licensing and subscription management endpoints
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from models.plugin_state import LicenseTier
from pydantic import BaseModel, Field

from core.database import get_db_pool
from core.license import check_plugin_license, get_plugin_license_tier, update_plugin_license

logger = logging.getLogger(__name__)

router = APIRouter()


class UpdateLicenseRequest(BaseModel):
    """Update plugin license request"""

    license_tier: LicenseTier
    license_key: Optional[str] = None


class LicenseValidationResponse(BaseModel):
    """License validation response"""

    valid: bool
    tier: str
    message: str


@router.get("/plugins/{plugin_name}/license/tier")
async def get_plugin_tier(plugin_name: str):
    """Get plugin's required license tier"""
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            tier = await get_plugin_license_tier(conn, plugin_name)
            return {"plugin_name": plugin_name, "required_tier": tier.value}
    except Exception as e:
        logger.error(f"Failed to get license tier for {plugin_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get license tier: {str(e)}")


@router.post("/plugins/{plugin_name}/license/validate")
async def validate_plugin_license(plugin_name: str, license_key: Optional[str] = None):
    """
    Validate plugin license key

    Checks if license key is valid for plugin's required tier
    """
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            result = await check_plugin_license(conn, plugin_name, license_key)
            return LicenseValidationResponse(**result)
    except Exception as e:
        logger.error(f"Failed to validate license for {plugin_name}: {e}")
        raise HTTPException(status_code=500, detail=f"License validation failed: {str(e)}")


@router.patch("/plugins/{plugin_name}/license")
async def update_plugin_license_endpoint(plugin_name: str, request: UpdateLicenseRequest):
    """
    Update plugin's license information

    Used when user purchases a license or upgrades tier
    """
    db = await get_db_pool()

    try:
        async with db.acquire() as conn:
            result = await update_plugin_license(
                conn, plugin_name, request.license_tier, request.license_key
            )

            if not result:
                raise HTTPException(status_code=404, detail=f"Plugin {plugin_name} not found")

            return {
                "plugin_name": plugin_name,
                "license_tier": result["license_tier"],
                "license_key": result.get("license_key"),
                "updated_at": result["updated_at"],
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update license for {plugin_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update license: {str(e)}")
