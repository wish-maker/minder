# services/marketplace/tests/test_security.py
from services.marketplace.core.security import LicenseGenerator


def test_generate_license_key():
    """Test license key generation"""
    generator = LicenseGenerator()

    license_key = generator.generate_license_key(
        user_id="user-123", plugin_id="plugin-456", tier="pro"
    )

    # Should be in format XXXX-XXXX-XXXX-XXXX
    assert len(license_key) == 19  # 4*4 + 3 dashes
    assert license_key.count("-") == 3

    # Should be different each time
    license_key2 = generator.generate_license_key(
        user_id="user-123", plugin_id="plugin-456", tier="pro"
    )
    assert license_key != license_key2
