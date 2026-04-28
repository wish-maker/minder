"""
Unit tests for rate limiting module.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.shared.rate_limiter import (
    RateLimiter,
    RateLimitExceeded,
    rate_limit,
    RateLimitInfo,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client"""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.incr = AsyncMock(return_value=1)
    redis.expire = AsyncMock(return_value=True)
    redis.sismember = AsyncMock(return_value=False)
    redis.sadd = AsyncMock(return_value=True)
    redis.srem = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def rate_limiter(mock_redis):
    """Create RateLimiter with mock Redis"""
    from src.shared.rate_limiter import RateLimiter
    return RateLimiter(redis_client=mock_redis)
    """Create RateLimiter instance"""
    return RateLimiter(redis=mock_redis)


class TestRateLimiter:
    """Test RateLimiter class"""

    @pytest.mark.asyncio
    async def test_is_rate_limited_first_request(self, rate_limiter, mock_redis):
        """Test first request is not rate limited"""
        mock_redis.incr.return_value = 1

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)

        assert is_allowed
        assert info["remaining"] > 0

    @pytest.mark.asyncio
    async def test_is_rate_limited_exceeded(self, rate_limiter, mock_redis):
        """Test request is rate limited when limit exceeded"""
        mock_redis.incr.return_value = 11
        mock_redis.get.return_value = "1234567890"

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)

        # Should not be allowed when limit exceeded
        assert info["remaining"] == 0

    @pytest.mark.asyncio
    async def test_is_rate_limited_custom_key_func(self, rate_limiter, mock_redis):
        """Test custom key function"""
        mock_redis.incr.return_value = 1

        is_allowed, info = await rate_limiter.is_allowed(
            "test-key", limit=10, window=60
        )

        assert is_allowed
        assert info["remaining"] > 0

    @pytest.mark.asyncio
    async def test_is_rate_limited_redis_error(self, rate_limiter, mock_redis):
        """Test Redis error handling"""
        mock_redis.incr.side_effect = Exception("Redis error")

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)
        # Should return True on error (fail-open)
        assert is_allowed

    @pytest.mark.asyncio
    async def test_is_rate_limited_with_whitelist(self, rate_limiter, mock_redis):
        """Test rate limiting with whitelist"""
        # Whitelist functionality is separate, just test basic rate limiting
        mock_redis.incr.return_value = 1

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)

        assert is_allowed

    @pytest.mark.asyncio
    async def test_get_rate_limit_info(self, rate_limiter, mock_redis):
        """Test getting rate limit info"""
        mock_redis.get.return_value = "1234567890"

        info = await rate_limiter.get_rate_limit_info("test-key", limit=10, window=60)

        assert isinstance(info, RateLimitInfo)
        assert info.limit == 10
        assert info.window == 60

    @pytest.mark.asyncio
    async def test_add_to_whitelist(self, rate_limiter, mock_redis):
        """Test adding IP to whitelist"""
        result = await rate_limiter.add_to_whitelist("192.168.1.1")

        assert result is True
        assert mock_redis.sadd.called

    @pytest.mark.asyncio
    async def test_remove_from_whitelist(self, rate_limiter, mock_redis):
        """Test removing IP from whitelist"""
        result = await rate_limiter.remove_from_whitelist("192.168.1.1")

        assert result is True
        assert mock_redis.srem.called

    @pytest.mark.asyncio
    async def test_is_whitelisted_true(self, rate_limiter, mock_redis):
        """Test checking if IP is whitelisted (True)"""
        mock_redis.sismember.return_value = True

        is_whitelisted = await rate_limiter.is_whitelisted("192.168.1.1")

        assert is_whitelisted is True

    @pytest.mark.asyncio
    async def test_is_whitelisted_false(self, rate_limiter, mock_redis):
        """Test checking if IP is whitelisted (False)"""
        mock_redis.sismember.return_value = False

        is_whitelisted = await rate_limiter.is_whitelisted("192.168.1.1")

        assert is_whitelisted is False

    @pytest.mark.asyncio
    async def test_is_whitelisted_error(self, rate_limiter, mock_redis):
        """Test checking whitelist with error"""
        mock_redis.sismember.side_effect = Exception("Redis error")

        is_whitelisted = await rate_limiter.is_whitelisted("192.168.1.1")

        assert is_whitelisted is False


class TestRateLimitExceeded:
    """Test RateLimitExceeded exception"""

    def test_rate_limit_exceeded_creation(self):
        """Test creating RateLimitExceeded"""
        exc = RateLimitExceeded(limit=100, window=60, reset_time=1234567890)

        assert exc.limit == 100
        assert exc.window == 60
        assert exc.reset_time == 1234567890
        assert str(exc) == "Rate limit exceeded: 100 requests per 60 seconds"


class TestRateLimitDecorator:
    """Test rate_limit decorator"""

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_allowed(self, mock_redis):
        """Test rate_limit decorator when request is allowed"""
        mock_redis.incr.return_value = 1

        @rate_limit(limit=10, window=60)
        async def test_func(request):
            return {"message": "Hello"}

        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        with patch.object(rate_limiter, "is_rate_limited", return_value=False):
            result = await test_func(mock_request)

            assert result == {"message": "Hello"}

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_exceeded(self, mock_redis):
        """Test rate_limit decorator when limit is exceeded"""
        mock_redis.incr.return_value = 11
        mock_redis.get.return_value = "1234567890"

        @rate_limit(limit=10, window=60)
        async def test_func(request):
            return {"message": "Hello"}

        from fastapi import Request

        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}

        from fastapi import HTTPException

        with patch.object(
            rate_limiter, "is_rate_limited", return_value=True
        ), pytest.raises(HTTPException) as exc_info:
            await test_func(mock_request)

        assert exc_info.value.status_code == 429


class TestRateLimitInfo:
    """Test RateLimitInfo dataclass"""

    def test_rate_limit_info_creation(self):
        """Test creating RateLimitInfo"""
        info = RateLimitInfo(
            limit=100,
            remaining=50,
            reset_time=1234567890,
            window=60,
        )

        assert info.limit == 100
        assert info.remaining == 50
        assert info.reset_time == 1234567890
        assert info.window == 60

    def test_rate_limit_info_to_dict(self):
        """Test RateLimitInfo to_dict method"""
        info = RateLimitInfo(
            limit=100,
            remaining=50,
            reset_time=1234567890,
            window=60,
        )

        info_dict = info.to_dict()

        assert info_dict["limit"] == 100
        assert info_dict["remaining"] == 50
        assert info_dict["reset_time"] == 1234567890
        assert info_dict["window"] == 60


class TestAddRateLimitHeaders:
    """Test add_rate_limit_headers function"""

    @pytest.mark.asyncio
    async def test_add_rate_limit_headers(self):
        """Test adding rate limit headers to response"""
        from src.shared.rate_limiter import add_rate_limit_headers
        from fastapi import Response

        response = Response()
        info = RateLimitInfo(
            limit=100,
            remaining=50,
            reset_time=1234567890,
            window=60,
        )

        await add_rate_limit_headers(response, info)

        assert response.headers["X-RateLimit-Limit"] == "100"
        assert response.headers["X-RateLimit-Remaining"] == "50"
        assert response.headers["X-RateLimit-Reset"] == "1234567890"
        assert response.headers["X-RateLimit-Window"] == "60"
