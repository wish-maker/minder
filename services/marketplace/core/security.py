# services/marketplace/core/security.py
import hashlib
import hmac
import os
import time
from typing import Dict

from services.marketplace.config import settings


class LicenseGenerator:
    """Generate and validate secure license keys"""

    def __init__(self):
        # In-memory store for license data (in production, use Redis/database)
        self._license_store: Dict[str, Dict] = {}

    def generate_license_key(self, user_id: str, plugin_id: str, tier: str) -> str:
        """
        Generate a secure license key (format: XXXX-XXXX-XXXX-XXXX)

        The key is a random token. License data is stored internally and
        can be retrieved during validation.
        """
        # 1. Create payload with timestamp and nonce
        timestamp = int(time.time())
        nonce = os.urandom(8).hex()
        payload = f"{user_id}:{plugin_id}:{tier}:{timestamp}:{nonce}"

        # 2. Generate HMAC signature
        secret = settings.LICENSE_SECRET
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

        # 3. Create license key from signature (take first 16 chars)
        key = signature[:16].upper()
        formatted = "-".join([key[i : i + 4] for i in range(0, 16, 4)])

        # 4. Store license data for later validation
        self._license_store[formatted] = {
            "user_id": user_id,
            "plugin_id": plugin_id,
            "tier": tier,
            "issued_at": timestamp,
        }

        return formatted

    def validate_license_key(self, license_key: str) -> Dict:
        """
        Validate a license key by looking it up in the license store.

        Returns the actual license data from the key if valid.
        """
        try:
            # 1. Basic format validation
            if len(license_key) != 19 or license_key.count("-") != 3:
                return {"valid": False, "reason": "invalid_format"}

            parts = license_key.split("-")
            if not all(len(p) == 4 for p in parts):
                return {"valid": False, "reason": "invalid_format"}

            # 2. Validate hex characters
            combined = license_key.replace("-", "")
            if not all(c in "0123456789ABCDEFabcdef" for c in combined):
                return {"valid": False, "reason": "invalid_format"}

            # 3. Look up license data from store
            license_data = self._license_store.get(license_key)
            if not license_data:
                return {"valid": False, "reason": "license_not_found"}

            # 4. Return actual license data
            return {
                "valid": True,
                "user_id": license_data["user_id"],
                "plugin_id": license_data["plugin_id"],
                "tier": license_data["tier"],
                "issued_at": license_data["issued_at"],
            }

        except Exception as e:
            return {"valid": False, "reason": str(e)}
