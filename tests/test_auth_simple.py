"""
Simplified Unit Tests for Authentication System
Tests JWT authentication and user management
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

from api.auth import AuthManager

# Test configuration
TEST_SECRET_KEY = "test_secret_key_for_testing_purposes_only"


class TestAuthManager:
    """Test AuthManager functionality"""

    def test_auth_manager_creation(self):
        """Test AuthManager initialization"""
        auth_manager = AuthManager()
        assert auth_manager is not None
        assert auth_manager.users is not None
        assert "admin" in auth_manager.users

    def test_default_admin_user(self):
        """Test default admin user is created"""
        auth_manager = AuthManager()
        assert "admin" in auth_manager.users
        assert auth_manager.users["admin"]["role"] == "admin"

    def test_create_access_token(self):
        """Test JWT token creation"""
        # Temporarily use test secret key
        import api.auth as auth_module
        original_secret = auth_module.SECRET_KEY
        auth_module.SECRET_KEY = TEST_SECRET_KEY

        try:
            auth_manager = AuthManager()
            data = {"sub": "admin"}
            token = auth_manager.create_access_token(data)

            # Token should be a string
            assert isinstance(token, str)
            # Token should have 3 parts
            assert len(token.split(".")) == 3

            # Decode and verify
            payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])
            assert payload.get("sub") == "admin"
            assert "exp" in payload
        finally:
            auth_module.SECRET_KEY = original_secret

    def test_token_expiration(self):
        """Test token has correct expiration"""
        import api.auth as auth_module
        original_secret = auth_module.SECRET_KEY
        auth_module.SECRET_KEY = TEST_SECRET_KEY

        try:
            auth_manager = AuthManager()
            data = {"sub": "admin"}
            token = auth_manager.create_access_token(data)

            payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])
            exp_time = datetime.fromtimestamp(payload["exp"])

            # Should be ~30 minutes in future
            time_until_exp = (exp_time - datetime.utcnow()).total_seconds()
            assert 1700 <= time_until_exp <= 1900
        finally:
            auth_module.SECRET_KEY = original_secret

    def test_verify_valid_token(self):
        """Test verification of valid token"""
        import api.auth as auth_module
        original_secret = auth_module.SECRET_KEY
        auth_module.SECRET_KEY = TEST_SECRET_KEY

        try:
            auth_manager = AuthManager()
            data = {"sub": "admin"}
            token = auth_manager.create_access_token(data)

            async def verify():
                payload = await auth_manager.verify_token(token)
                assert payload is not None
                assert payload.get("username") == "admin"

            asyncio.run(verify())
        finally:
            auth_module.SECRET_KEY = original_secret

    def test_verify_invalid_token(self):
        """Test verification of invalid token"""
        auth_manager = AuthManager()
        invalid_token = "invalid.token.string"

        async def verify():
            payload = await auth_manager.verify_token(invalid_token)
            assert payload is None

        asyncio.run(verify())

    def test_authenticate_valid_user(self):
        """Test authentication with valid credentials"""
        auth_manager = AuthManager()

        async def authenticate():
            result = await auth_manager.authenticate("admin", "admin123")
            assert result is not None
            assert result.get("username") == "admin"
            assert result.get("role") == "admin"

        asyncio.run(authenticate())

    def test_authenticate_invalid_user(self):
        """Test authentication with invalid credentials"""
        auth_manager = AuthManager()

        async def authenticate():
            result = await auth_manager.authenticate("nonexistent", "wrong_password")
            assert result is None

        asyncio.run(authenticate())

    def test_authenticate_wrong_password(self):
        """Test authentication with wrong password"""
        auth_manager = AuthManager()

        async def authenticate():
            result = await auth_manager.authenticate("admin", "wrong_password")
            assert result is None

        asyncio.run(authenticate())


class TestPasswordHashing:
    """Test password hashing using bcrypt"""

    def test_password_hashing(self):
        """Test password hashing"""
        password = "test_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) > 50

    def test_password_verification(self):
        """Test password verification"""
        password = "test_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Correct password should verify
        assert bcrypt.checkpw(password.encode(), hashed.encode()) is True

        # Wrong password should not verify
        assert bcrypt.checkpw("wrong_password".encode(), hashed.encode()) is False

    def test_hash_uniqueness(self):
        """Test that same password generates different hashes"""
        password = "test_password_123"
        hash1 = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        hash2 = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Different hashes due to salt
        assert hash1 != hash2

        # But both verify correctly
        assert bcrypt.checkpw(password.encode(), hash1.encode()) is True
        assert bcrypt.checkpw(password.encode(), hash2.encode()) is True


class TestTokenSecurity:
    """Test JWT token security features"""

    def test_token_contains_expiration(self):
        """Test token includes expiration"""
        import api.auth as auth_module
        original_secret = auth_module.SECRET_KEY
        auth_module.SECRET_KEY = TEST_SECRET_KEY

        try:
            auth_manager = AuthManager()
            data = {"sub": "admin"}
            token = auth_manager.create_access_token(data)

            payload = jwt.decode(token, TEST_SECRET_KEY, algorithms=["HS256"])
            assert "exp" in payload
            assert "iat" in payload
            assert payload.get("sub") == "admin"
        finally:
            auth_module.SECRET_KEY = original_secret

    def test_password_not_plaintext(self):
        """Test passwords are hashed, not plaintext"""
        password = "sensitive_password_123"
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        # Password should not be in hash
        assert password not in hashed
        # Hash should be longer
        assert len(hashed) > len(password)


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
