"""
Unit tests for Redis client utilities
"""
import pytest
from unittest.mock import Mock, patch
import redis

from services.shared.utils.redis_client import (
    create_redis_client,
    create_redis_client_from_settings,
)


class TestCreateRedisClient:
    """Test create_redis_client function"""

    def test_create_redis_client_basic(self):
        """Test basic Redis client creation"""
        with patch("services.shared.utils.redis_client.redis.Redis") as mock_redis:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_redis.return_value = mock_client

            client = create_redis_client(host="localhost", port=6379)

            # Verify Redis was initialized correctly
            mock_redis.assert_called_once_with(
                host="localhost",
                port=6379,
                password=None,
                decode_responses=True,
                db=0,
            )

            # Verify ping was called
            mock_client.ping.assert_called_once()

            assert client == mock_client

    def test_create_redis_client_with_password(self):
        """Test Redis client creation with password"""
        with patch("services.shared.utils.redis_client.redis.Redis") as mock_redis:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_redis.return_value = mock_client

            client = create_redis_client(
                host="localhost",
                port=6379,
                password="secret"
            )

            mock_redis.assert_called_once_with(
                host="localhost",
                port=6379,
                password="secret",
                decode_responses=True,
                db=0,
            )

            assert client == mock_client

    def test_create_redis_client_connection_failure(self):
        """Test Redis client creation raises on connection failure"""
        with patch("services.shared.utils.redis_client.redis.Redis") as mock_redis:
            mock_client = Mock()
            mock_client.ping.side_effect = ConnectionError("Connection refused")
            mock_redis.return_value = mock_client

            with pytest.raises(ConnectionError):
                create_redis_client(host="localhost", port=6379)

    def test_create_redis_client_custom_db(self):
        """Test Redis client creation with custom database"""
        with patch("services.shared.utils.redis_client.redis.Redis") as mock_redis:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_redis.return_value = mock_client

            client = create_redis_client(host="localhost", port=6379, db=1)

            mock_redis.assert_called_once_with(
                host="localhost",
                port=6379,
                password=None,
                decode_responses=True,
                db=1,
            )

            assert client == mock_client

    def test_create_redis_client_no_decode(self):
        """Test Redis client creation without decode_responses"""
        with patch("services.shared.utils.redis_client.redis.Redis") as mock_redis:
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_redis.return_value = mock_client

            client = create_redis_client(
                host="localhost",
                port=6379,
                decode_responses=False
            )

            mock_redis.assert_called_once_with(
                host="localhost",
                port=6379,
                password=None,
                decode_responses=False,
                db=0,
            )

            assert client == mock_client


class TestCreateRedisClientFromSettings:
    """Test create_redis_client_from_settings function"""

    def test_create_from_settings_basic(self):
        """Test creating client from settings object"""
        mock_settings = Mock()
        mock_settings.REDIS_HOST = "redis-server"
        mock_settings.REDIS_PORT = 6379
        mock_settings.REDIS_PASSWORD = "password"

        with patch("services.shared.utils.redis_client.create_redis_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            client = create_redis_client_from_settings(mock_settings)

            # Verify create_redis_client was called with correct params
            mock_create.assert_called_once_with(
                host="redis-server",
                port=6379,
                password="password",
                decode_responses=True,
                db=0,
            )

            assert client == mock_client

    def test_create_from_settings_defaults(self):
        """Test creating client with default values"""
        mock_settings = Mock()
        # Settings object missing attributes
        delattr(mock_settings, "REDIS_HOST")
        delattr(mock_settings, "REDIS_PORT")
        delattr(mock_settings, "REDIS_PASSWORD")

        with patch("services.shared.utils.redis_client.create_redis_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            client = create_redis_client_from_settings(mock_settings)

            # Verify defaults were used
            mock_create.assert_called_once_with(
                host="localhost",
                port=6379,
                password=None,
                decode_responses=True,
                db=0,
            )

            assert client == mock_client

    def test_create_from_settings_with_none_password(self):
        """Test creating client when password is None"""
        mock_settings = Mock()
        mock_settings.REDIS_HOST = "redis-server"
        mock_settings.REDIS_PORT = 6379
        mock_settings.REDIS_PASSWORD = None

        with patch("services.shared.utils.redis_client.create_redis_client") as mock_create:
            mock_client = Mock()
            mock_create.return_value = mock_client

            client = create_redis_client_from_settings(mock_settings)

            mock_create.assert_called_once_with(
                host="redis-server",
                port=6379,
                password=None,
                decode_responses=True,
                db=0,
            )

            assert client == mock_client


@pytest.mark.integration
class TestRedisClientIntegration:
    """Integration tests for Redis client (require real Redis)"""

    @pytest.mark.redis
    def test_real_redis_connection(self, test_settings):
        """Test connection to real Redis instance"""
        try:
            client = create_redis_client_from_settings(test_settings)
            assert client.ping() is True
        except ConnectionError:
            pytest.skip("Redis not available")

    @pytest.mark.redis
    def test_real_redis_operations(self, test_settings):
        """Test basic operations on real Redis"""
        try:
            client = create_redis_client_from_settings(test_settings)

            # Test set/get
            client.set("test_key", "test_value")
            assert client.get("test_key") == "test_value"

            # Test delete
            client.delete("test_key")
            assert client.get("test_key") is None

        except ConnectionError:
            pytest.skip("Redis not available")
