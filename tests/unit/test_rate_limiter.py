"""
Unit tests for rate limiting module.
"""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.shared.rate_limiter import RateLimitExceeded, RateLimitInfo, rate_limit


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
    redis.zcount = AsyncMock(return_value=0)
    # Configure pipeline mock
    redis.pipeline = Mock(return_value=create_mock_pipeline(0))
    return redis


@pytest.fixture
def rate_limiter(mock_redis):
    """Create RateLimiter instance"""
    from src.shared.rate_limiter import RateLimiter as RL

    return RL(redis_client=mock_redis)


def create_mock_pipeline(zcard_result=0):
    """Helper to create a properly configured mock pipeline"""
    mock_pipeline = AsyncMock()
    mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
    mock_pipeline.__aexit__ = AsyncMock(return_value=None)

    # Configure pipeline methods to be regular methods (not coroutines)
    def sync_zremrangebyscore(*args, **kwargs):
        return 0

    def sync_zcard(*args, **kwargs):
        return zcard_result

    def sync_zadd(*args, **kwargs):
        return 1

    def sync_expire(*args, **kwargs):
        return True

    mock_pipeline.zremrangebyscore = sync_zremrangebyscore
    mock_pipeline.zcard = sync_zcard
    mock_pipeline.zadd = sync_zadd
    mock_pipeline.expire = sync_expire
    mock_pipeline.execute = AsyncMock(return_value=[0, zcard_result, 1, True])
    return mock_pipeline


class TestRateLimiter:
    """Test RateLimiter class"""

    @pytest.mark.asyncio
    async def test_is_rate_limited_first_request(self, rate_limiter, mock_redis):
        """Test first request is not rate limited"""
        # Mock pipeline to return count of 0 (no requests yet)
        mock_pipeline = create_mock_pipeline(zcard_result=0)
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)

        assert is_allowed
        assert info["remaining"] == 10  # 10 - 0 = 10 remaining

    @pytest.mark.asyncio
    async def test_is_rate_limited_exceeded(self, rate_limiter, mock_redis):
        """Test request is rate limited when limit exceeded"""
        # Mock pipeline to return count of 10 (at limit)
        mock_pipeline = create_mock_pipeline(zcard_result=10)
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)

        # Should not be allowed when at limit (10 >= 10)
        assert not is_allowed
        assert info["remaining"] == 0
        assert info["current_count"] == 10

    @pytest.mark.asyncio
    async def test_is_rate_limited_custom_key_func(self, rate_limiter, mock_redis):
        """Test custom key function"""
        # Mock pipeline to return count of 3
        mock_pipeline = create_mock_pipeline(zcard_result=3)
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        is_allowed, info = await rate_limiter.is_allowed("custom-key", limit=10, window=60)

        assert is_allowed
        assert info["remaining"] == 7  # 10 - 3 = 7 remaining

    @pytest.mark.asyncio
    async def test_is_rate_limited_redis_error(self, rate_limiter, mock_redis):
        """Test Redis error handling"""
        # Mock pipeline to raise exception when execute is called
        failing_pipeline = create_mock_pipeline(zcard_result=0)
        failing_pipeline.execute = AsyncMock(side_effect=Exception("Redis error"))
        mock_redis.pipeline.return_value = failing_pipeline

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)
        # Should return True on error (fail-open)
        assert is_allowed

    @pytest.mark.asyncio
    async def test_is_rate_limited_with_whitelist(self, rate_limiter, mock_redis):
        """Test rate limiting with whitelist"""
        # Mock pipeline to return count of 2
        mock_pipeline = create_mock_pipeline(zcard_result=2)
        mock_redis.pipeline = Mock(return_value=mock_pipeline)

        is_allowed, info = await rate_limiter.is_allowed("test-key", limit=10, window=60)

        assert is_allowed
        assert info["remaining"] == 8  # 10 - 2 = 8 remaining

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
        """Test rate limit decorator when request is allowed"""

        @rate_limit(limit=10, window=60)
        async def test_func(request):
            return {"message": "Hello"}

        from fastapi import Request

        # Create mock app with rate limiter
        mock_limiter = AsyncMock()
        mock_limiter.is_allowed = AsyncMock(return_value=(True, {"remaining": 9, "reset_time": 1234567890}))

        mock_app = MagicMock()
        mock_app.state.rate_limiter = mock_limiter

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}
        mock_request.app = mock_app
        mock_request.app.state = mock_app.state

        # Execute
        result = await test_func(mock_request)

        # Assert
        assert result == {"message": "Hello"}
        mock_limiter.is_allowed.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limit_decorator_exceeded(self, mock_redis):
        """Test rate limit decorator when limit is exceeded"""

        @rate_limit(limit=10, window=60)
        async def test_func(request):
            return {"message": "Hello"}

        from fastapi import HTTPException, Request

        # Create mock app with rate limiter
        mock_limiter = AsyncMock()
        mock_limiter.is_allowed = AsyncMock(return_value=(False, {"remaining": 0, "reset_time": 1234567890}))

        mock_app = MagicMock()
        mock_app.state.rate_limiter = mock_limiter

        # Create mock request
        mock_request = MagicMock(spec=Request)
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}
        mock_request.app = mock_app
        mock_request.app.state = mock_app.state

        # Execute and assert exception
        with pytest.raises(HTTPException) as exc_info:
            await test_func(mock_request)

        # Assert
        assert exc_info.value.status_code == 429
        mock_limiter.is_allowed.assert_called_once()


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
        from fastapi import Response

        from src.shared.rate_limiter import add_rate_limit_headers

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
