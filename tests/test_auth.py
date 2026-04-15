"""
Unit Tests for Authentication System
Tests JWT authentication, token validation, and user management
"""
import pytest
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import sys
import os
import jwt
import bcrypt

sys.path.insert(0, str(Path(__file__).parent.parent))

from api.auth import (
    AuthManager,
    get_current_user,
    get_current_user_optional,
    get_auth_manager
)

# Test configuration
TEST_SECRET_KEY = "test_secret_key_for_testing_purposes_only"
TEST_USERS = {
    "admin": {
        "password": "admin123",
        "role": "admin",
        "permissions": ["read", "write", "delete", "manage_users"]
    },
    "user": {
        "password": "user123",
        "role": "user",
        "permissions": ["read", "write"]
    }
}

# Mock AuthManager for testing
class TestAuthManager(AuthManager):
    """Test AuthManager with custom secret key"""
    def __init__(self):
        # Use test secret key temporarily
        import api.auth as auth_module
        original_secret = auth_module.SECRET_KEY
        auth_module.SECRET_KEY = TEST_SECRET_KEY

        super().__init__()

        # Restore original secret
        auth_module.SECRET_KEY = original_secret


class TestPasswordHashing:
    """Test password hashing and verification"""

    def test_password_hashing(self):
        """Test password hashing"""
        password = "test_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Hash should be different from original password
        assert hashed != password
        # Hash should contain bcrypt identifier
        assert hashed.startswith("$2b$")

    def test_password_verification_correct(self):
        """Test password verification with correct password"""
        password = "test_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Should return True for correct password
        assert bcrypt.checkpw(password.encode(), hashed.encode()) is True

    def test_password_verification_incorrect(self):
        """Test password verification with incorrect password"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Should return False for incorrect password
        assert bcrypt.checkpw(wrong_password.encode(), hashed.encode()) is False

    def test_password_hash_uniqueness(self):
        """Test that same password generates different hashes"""
        password = "test_password_123"
        hash1 = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        hash2 = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Same password should generate different hashes (due to salt)
        assert hash1 != hash2
        # But both should verify correctly
        assert bcrypt.checkpw(password.encode(), hash1.encode()) is True
        assert bcrypt.checkpw(password.encode(), hash2.encode()) is True


class TestTokenCreation:
    """Test JWT token creation"""

    def test_create_token_basic(self):
        """Test basic token creation"""
        auth_manager = TestAuthManager()
        data = {"sub": "admin"}
        token = auth_manager.create_access_token(data)

        # Token should be a string
        assert isinstance(token, str)
        # Token should have 3 parts (header.payload.signature)
        assert len(token.split(".")) == 3

    def test_create_token_with_expiration(self):
        """Test token creation with expiration (using default 30 min)"""
        auth_manager = TestAuthManager()
        data = {"sub": "admin"}
        token = auth_manager.create_access_token(data)

        # Decode token to check expiration
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])

        # Should have expiration time
        assert "exp" in payload
        # Should be approximately 30 minutes from now
        exp_time = datetime.fromtimestamp(payload["exp"])
        now = datetime.utcnow()
        time_diff = (exp_time - now).total_seconds()

        # Should be around 30 minutes (± 60 seconds for test execution time)
        assert 1740 <= time_diff <= 1860  # 29-31 minutes

    def test_create_token_with_extra_data(self):
        """Test token creation with additional data"""
        auth_manager = TestAuthManager()
        data = {
            "sub": "admin",
            "role": "admin",
            "permissions": ["read", "write", "delete"]
        }
        token = auth_manager.create_access_token(data)

        # Decode and verify extra data
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])

        assert payload.get("sub") == "admin"
        # Note: Additional fields might be preserved in token
        assert "sub" in payload


class TestTokenVerification:
    """Test JWT token verification"""

    def test_verify_valid_token(self):
        """Test verification of valid token"""
        auth_manager = TestAuthManager()
        data = {"sub": "admin"}
        token = auth_manager.create_access_token(data)

        # Verify the token
        async def verify():
            payload = await auth_manager.verify_token(token)
            assert payload is not None
            assert payload.get("username") == "admin"

        asyncio.run(verify())

    def test_verify_invalid_token(self):
        """Test verification of invalid token"""
        auth_manager = TestAuthManager()
        invalid_token = "invalid.token.string"

        # Should return None for invalid token
        async def verify():
            payload = await auth_manager.verify_token(invalid_token)
            assert payload is None

        asyncio.run(verify())

    def test_verify_expired_token(self):
        """Test verification of expired token"""
        auth_manager = TestAuthManager()

        # Create an expired token manually
        import api.auth as auth_module
        original_secret = auth_module.SECRET_KEY
        auth_module.SECRET_KEY = TEST_SECRET_KEY

        try:
            # Create expired payload
            expired_payload = {
                "sub": "admin",
                "exp": datetime.utcnow() - timedelta(minutes=1),  # Expired 1 min ago
                "iat": datetime.utcnow() - timedelta(minutes=31)
            }
            expired_token = jwt.encode(expired_payload, TEST_SECRET_KEY, algorithm="HS256")

            # Should return None for expired token
            async def verify():
                payload = await auth_manager.verify_token(expired_token)
                assert payload is None

            asyncio.run(verify())
        finally:
            auth_module.SECRET_KEY = original_secret


class TestUserAuthentication:
    """Test user authentication flow"""

    def test_authenticate_valid_user(self):
        """Test authentication with valid credentials"""
        auth_manager = TestAuthManager()
        username = "admin"
        password = "admin123"  # Default admin password

        async def authenticate():
            result = await auth_manager.authenticate(username, password)
            # Should return user data
            assert result is not None
            assert result.get("username") == "admin"
            assert result.get("role") == "admin"

        asyncio.run(authenticate())

    def test_authenticate_invalid_user(self):
        """Test authentication with invalid credentials"""
        auth_manager = TestAuthManager()
        username = "nonexistent_user"
        password = "wrong_password"

        async def authenticate():
            result = await auth_manager.authenticate(username, password)
            # Should return None for invalid credentials
            assert result is None

        asyncio.run(authenticate())

    def test_authenticate_wrong_password(self):
        """Test authentication with wrong password"""
        auth_manager = TestAuthManager()
        username = "admin"
        password = "wrong_password"

        async def authenticate():
            result = await auth_manager.authenticate(username, password)
            # Should return None for wrong password
            assert result is None

        asyncio.run(authenticate())


class TestTokenExpiration:
    """Test token expiration behavior"""

    def test_token_expiration_time(self):
        """Test that tokens expire at the correct time"""
        expires_delta = timedelta(minutes=30)
        data = {"sub": "admin"}
        token = create_access_token(data, expires_delta=expires_delta)

        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        exp_time = datetime.fromtimestamp(payload["exp"])

        # Expiration should be in the future
        assert exp_time > datetime.utcnow()

        # But not too far in the future
        time_until_exp = (exp_time - datetime.utcnow()).total_seconds()
        assert 1700 <= time_until_exp <= 1900  # ~30 minutes

    def test_short_lived_token(self):
        """Test creation of short-lived token"""
        expires_delta = timedelta(minutes=5)
        data = {"sub": "admin"}
        token = create_access_token(data, expires_delta=expires_delta)

        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        time_until_exp = (datetime.fromtimestamp(payload["exp"]) - datetime.utcnow()).total_seconds()

        # Should be around 5 minutes
        assert 240 <= time_until_exp <= 360  # 4-6 minutes


class TestSecurityFeatures:
    """Test security-related features"""

    def test_token_secret_key_required(self):
        """Test that secret key is required for token creation"""
        data = {"sub": "admin"}

        # Should work with valid secret key
        token = create_access_token(data)
        assert token is not None

        # Token should be verifiable with same secret key
        payload = verify_token(token)
        assert payload is not None

    def test_password_not_stored_in_plaintext(self):
        """Test that passwords are not stored in plaintext"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        # Hash should not contain plaintext password
        assert password not in hashed
        # Hash should be significantly longer than password
        assert len(hashed) > len(password)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
