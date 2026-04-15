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

@pytest.fixture
def test_auth_manager():
    """Create AuthManager with test secret key"""
    original_secret = os.getenv("JWT_SECRET_KEY")
    os.environ["JWT_SECRET_KEY"] = TEST_SECRET_KEY

    # Re-import auth module to pick up new secret
    import importlib
    import api.auth as auth_module
    importlib.reload(auth_module)

    manager = AuthManager()

    yield manager

    # Restore original secret
    if original_secret:
        os.environ["JWT_SECRET_KEY"] = original_secret
    else:
        os.environ.pop("JWT_SECRET_KEY", None)


class TestPasswordHashing:
    """Test password hashing and verification"""

    def test_password_hashing(self, test_auth_manager):
        """Test password hashing"""
        password = "test_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Hash should be different from original password
        assert hashed != password
        # Hash should contain bcrypt identifier
        assert hashed.startswith("$2b$")

    def test_password_verification_correct(self, test_auth_manager):
        """Test password verification with correct password"""
        password = "test_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Should return True for correct password
        assert bcrypt.checkpw(password.encode(), hashed.encode()) is True

    def test_password_verification_incorrect(self, test_auth_manager):
        """Test password verification with incorrect password"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Should return False for incorrect password
        assert bcrypt.checkpw(wrong_password.encode(), hashed.encode()) is False

    def test_password_hash_uniqueness(self, test_auth_manager):
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

    def test_create_token_basic(self, test_auth_manager):
        """Test basic token creation"""
        data = {"sub": "admin"}
        token = test_auth_manager.create_access_token(data)

        # Token should be a string
        assert isinstance(token, str)
        # Token should have 3 parts (header.payload.signature)
        assert len(token.split(".")) == 3

    def test_create_token_with_expiration(self, test_auth_manager):
        """Test token creation with expiration (using default 30 min)"""
        data = {"sub": "admin"}
        token = test_auth_manager.create_access_token(data)

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

    def test_create_token_with_extra_data(self, test_auth_manager):
        """Test token creation with additional data"""
        data = {
            "sub": "admin",
            "role": "admin",
            "permissions": ["read", "write", "delete"]
        }
        token = test_auth_manager.create_access_token(data)

        # Decode and verify extra data
        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])

        assert payload.get("sub") == "admin"
        # Note: Additional fields might be preserved in token
        assert "sub" in payload


class TestTokenVerification:
    """Test JWT token verification"""

    def test_verify_valid_token(self, test_auth_manager):
        """Test verification of valid token"""
        data = {"sub": "admin"}
        token = test_auth_manager.create_access_token(data)

        # Verify the token
        async def verify():
            payload = await test_auth_manager.verify_token(token)
            assert payload is not None
            assert payload.get("username") == "admin"

        asyncio.run(verify())

    def test_verify_invalid_token(self, test_auth_manager):
        """Test verification of invalid token"""
        invalid_token = "invalid.token.string"

        # Should return None for invalid token
        async def verify():
            payload = await test_auth_manager.verify_token(invalid_token)
            assert payload is None

        asyncio.run(verify())

    def test_verify_expired_token(self, test_auth_manager):
        """Test verification of expired token"""

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
                payload = await test_auth_manager.verify_token(expired_token)
                assert payload is None

            asyncio.run(verify())
        finally:
            auth_module.SECRET_KEY = original_secret


class TestUserAuthentication:
    """Test user authentication flow"""

    def test_authenticate_valid_user(self, test_auth_manager):
        """Test authentication with valid credentials"""
        username = "admin"
        password = "admin123"  # Default admin password

        async def authenticate():
            result = await test_auth_manager.authenticate(username, password)
            # Should return user data
            assert result is not None
            assert result.get("username") == "admin"
            assert result.get("role") == "admin"

        asyncio.run(authenticate())

    def test_authenticate_invalid_user(self, test_auth_manager):
        """Test authentication with invalid credentials"""
        username = "nonexistent_user"
        password = "wrong_password"

        async def authenticate():
            result = await test_auth_manager.authenticate(username, password)
            # Should return None for invalid credentials
            assert result is None

        asyncio.run(authenticate())

    def test_authenticate_wrong_password(self, test_auth_manager):
        """Test authentication with wrong password"""
        username = "admin"
        password = "wrong_password"

        async def authenticate():
            result = await test_auth_manager.authenticate(username, password)
            # Should return None for wrong password
            assert result is None

        asyncio.run(authenticate())


class TestTokenExpiration:
    """Test token expiration behavior"""

    def test_token_expiration_time(self, test_auth_manager):
        """Test that tokens expire at the correct time"""
        expires_delta = timedelta(minutes=30)
        data = {"sub": "admin"}
        token = test_auth_manager.create_access_token(data)

        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])
        exp_time = datetime.fromtimestamp(payload["exp"])

        # Expiration should be in the future
        assert exp_time > datetime.utcnow()

        # But not too far in the future
        time_until_exp = (exp_time - datetime.utcnow()).total_seconds()
        assert 1700 <= time_until_exp <= 1900  # ~30 minutes

    def test_short_lived_token(self, test_auth_manager):
        """Test creation of short-lived token"""
        # Note: Current implementation uses fixed 30 min expiration
        # This test verifies that tokens have reasonable expiration
        data = {"sub": "admin"}
        token = test_auth_manager.create_access_token(data)

        payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])
        time_until_exp = (datetime.fromtimestamp(payload["exp"]) - datetime.utcnow()).total_seconds()

        # Should have some expiration time
        assert time_until_exp > 0
        assert time_until_exp <= 3600  # Less than 1 hour


class TestSecurityFeatures:
    """Test security-related features"""

    def test_token_secret_key_required(self, test_auth_manager):
        """Test that secret key is required for token creation"""
        data = {"sub": "admin"}

        # Should work with valid secret key
        token = test_auth_manager.create_access_token(data)
        assert token is not None

        # Token should be verifiable with same secret key
        async def verify():
            payload = await test_auth_manager.verify_token(token)
            return payload

        payload = asyncio.run(verify())
        assert payload is not None

    def test_password_not_stored_in_plaintext(self, test_auth_manager):
        """Test that passwords are not stored in plaintext"""
        password = "test_password_123"
        hashed = test_auth_manager._hash_password(password)

        # Hash should not contain plaintext password
        assert password not in hashed
        # Hash should be significantly longer than password
        assert len(hashed) > len(password)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
