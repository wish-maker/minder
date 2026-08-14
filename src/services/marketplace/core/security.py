# services/marketplace/core/security.py
import hashlib
import hmac
import os
import time

from config import settings


class LicenseGenerator:
    """Generate secure license keys.

    Real validation lives in core/licensing.py's validate_license(), which
    checks the key against the persistent marketplace_licenses Postgres table
    (expiry, active flag, usage tracking). This class used to also carry a
    validate_license_key() that looked keys up in a per-instance in-memory
    dict populated by generate_license_key() -- dead code (nothing called it
    outside its own test) and broken by construction even if it had been
    called: the dict lives only as long as one process, so it would report
    "license_not_found" for every key issued before the last restart, and
    would never agree across horizontally-scaled replicas. Removed rather
    than fixed, since the real, working validation path already exists.
    """

    def generate_license_key(self, user_id: str, plugin_id: str, tier: str) -> str:
        """
        Generate a secure license key (format: XXXX-XXXX-XXXX-XXXX)

        The key is an HMAC-derived token; the caller (core/licensing.py) persists
        it alongside user_id/plugin_id/tier for later lookup.
        """
        # 1. Create payload with timestamp and nonce
        timestamp = int(time.time())
        nonce = os.urandom(8).hex()
        payload = f"{user_id}:{plugin_id}:{tier}:{timestamp}:{nonce}"

        # 2. Generate HMAC signature (LICENSE_SECRET, or JWT_SECRET as fallback —
        #    no weak hardcoded default; see config.LICENSE_SECRET).
        secret = settings.LICENSE_SECRET or settings.JWT_SECRET
        signature = hmac.new(
            secret.encode(), payload.encode(), hashlib.sha256
        ).hexdigest()

        # 3. Create license key from signature (take first 16 chars)
        key = signature[:16].upper()
        return "-".join([key[i : i + 4] for i in range(0, 16, 4)])
