# services/marketplace/tests/test_security.py
from services.marketplace.core.security import LicenseGenerator


def test_generate_license_key():
    """Test license key generation"""
    generator = LicenseGenerator()

    license_key = generator.generate_license_key(user_id="user-123", plugin_id="plugin-456", tier="professional")

    # Should be in format XXXX-XXXX-XXXX-XXXX
    assert len(license_key) == 19  # 4*4 + 3 dashes
    assert license_key.count("-") == 3

    # Should be different each time
    license_key2 = generator.generate_license_key(user_id="user-123", plugin_id="plugin-456", tier="professional")
    assert license_key != license_key2


def test_validate_license_key():
    """Test license key validation"""
    generator = LicenseGenerator()

    # Generate valid license
    license_key = generator.generate_license_key(user_id="user-123", plugin_id="plugin-456", tier="professional")

    # Validate it
    result = generator.validate_license_key(license_key)

    assert result["valid"] is True
    assert result["user_id"] == "user-123"
    assert result["plugin_id"] == "plugin-456"
    assert result["tier"] == "professional"


def test_validate_invalid_license_key():
    """Test validation of invalid license key"""
    generator = LicenseGenerator()

    # Invalid format
    result = generator.validate_license_key("INVALID-KEY")

    assert result["valid"] is False
    assert "reason" in result


def test_validate_tampered_license_key():
    """Test validation of tampered license key"""
    generator = LicenseGenerator()

    # Generate valid license
    license_key = generator.generate_license_key(user_id="user-123", plugin_id="plugin-456", tier="professional")

    # Tamper with it
    tampered_key = license_key[:-1] + "X"

    result = generator.validate_license_key(tampered_key)

    assert result["valid"] is False
    assert result["reason"] in ["invalid_format", "invalid_signature"]
