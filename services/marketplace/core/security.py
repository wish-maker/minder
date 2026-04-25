# services/marketplace/core/security.py
import hashlib
import hmac
import os
import time
from typing import Dict

from services.marketplace.config import settings


class LicenseGenerator:
    """Generate and validate secure license keys"""

    def generate_license_key(self, user_id: str, plugin_id: str, tier: str) -> str:
        """Generate a secure license key (format: XXXX-XXXX-XXXX-XXXX)"""
        # 1. Create payload with timestamp for uniqueness
        timestamp = int(time.time() * 1000)  # milliseconds for more uniqueness
        nonce = os.urandom(8).hex()  # random nonce for uniqueness
        payload = f"{user_id}:{plugin_id}:{tier}:{timestamp}:{nonce}"

        # 2. Generate signature
        secret = settings.LICENSE_SECRET
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()

        # 3. Hash to create license key
        combined = payload.encode() + signature
        hash_obj = hashlib.sha256(combined)
        hash_hex = hash_obj.hexdigest()

        # 4. Format as XXXX-XXXX-XXXX-XXXX (using hex chars 0-9, A-F)
        # Take first 16 chars and ensure they're uppercase
        key = hash_hex[:16].upper()
        formatted = "-".join([key[i : i + 4] for i in range(0, 16, 4)])

        return formatted

    def validate_license_key(self, license_key: str) -> Dict:
        """
        Validate a license key

        Note: This is a simplified version. In production,
        you would look up the license in the database.
        """
        try:
            # Basic format validation
            if len(license_key) != 19 or license_key.count("-") != 3:
                return {"valid": False, "reason": "invalid_format"}

            parts = license_key.split("-")
            if not all(len(p) == 4 for p in parts):
                return {"valid": False, "reason": "invalid_format"}

            # Validate that all characters are valid hex (0-9, A-F)
            combined = license_key.replace("-", "")
            if not all(c in "0123456789ABCDEFabcdef" for c in combined):
                return {"valid": False, "reason": "invalid_format"}

            # In production, look up in database and verify signature
            # For now, return a test response for valid format
            return {
                "valid": True,
                "user_id": "user-123",
                "plugin_id": "plugin-456",
                "tier": "professional",
                "issued_at": int(time.time()),
            }

        except Exception as e:
            return {"valid": False, "reason": str(e)}
