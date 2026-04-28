"""
Unit tests for retry logic module.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.shared.retry.retry_logic import (
    retry,
    retry_async_operation,
    RetryError,
    with_circuit_breaker,
)
from src.shared.retry.retry_strategy import RetryStrategy, RetryPolicy
from src.shared.retry.circuit_breaker import CircuitBreaker, CircuitBreakerError


class TestRetryStrategy:
    """Test RetryStrategy enum"""

    def test_retry_strategy_none(self):
        """Test RetryStrategy.NONE"""
        assert RetryStrategy.NONE.value == "none"

    def test_retry_strategy_linear(self):
        """Test RetryStrategy.LINEAR"""
        assert RetryStrategy.LINEAR.value == "linear"

    def test_retry_strategy_exponential(self):
        """Test RetryStrategy.EXPONENTIAL"""
        assert RetryStrategy.EXPONENTIAL.value == "exponential"


class TestRetryPolicy:
    """Test RetryPolicy class"""

    def test_retry_policy_default(self):
        """Test RetryPolicy with defaults"""
        policy = RetryPolicy()

        assert policy.strategy == RetryStrategy.EXPONENTIAL
        assert policy.max_attempts == 3
        assert policy.base_delay == 1.0
        assert policy.max_delay == 30.0
        assert policy.backoff_multiplier == 2.0

    def test_calculate_delay_linear(self):
        """Test linear delay calculation"""
        policy = RetryPolicy(
            strategy=RetryStrategy.LINEAR,
            base_delay=1.0,
            max_delay=10.0,
        )
        delay = policy.calculate_delay(attempt=2)

        assert delay == 2.0

    def test_calculate_delay_exponential(self):
        """Test exponential delay calculation"""
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            max_delay=10.0,
        )
        delay = policy.calculate_delay(attempt=2)

        assert delay == 2.0  # 1.0 * 2^1

    def test_calculate_delay_max_delay(self):
        """Test delay capped at max_delay"""
        policy = RetryPolicy(
            strategy=RetryStrategy.EXPONENTIAL,
            base_delay=1.0,
            max_delay=10.0,
        )
        delay = policy.calculate_delay(attempt=10)

        assert delay == 10.0


class TestCircuitBreaker:
    """Test CircuitBreaker class"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_initially_closed(self):
        """Test circuit breaker starts in closed state"""
        breaker = CircuitBreaker(
            service_name="test_service",
            failure_threshold=5,
            success_threshold=3,
            timeout=60,
        )

        assert breaker.get_state() == "CLOSED"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_threshold(self):
        """Test circuit breaker opens after threshold failures"""
        breaker = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            success_threshold=3,
            timeout=60,
        )

        for _ in range(3):
            breaker.record_failure()

        assert breaker.get_state() == "OPEN"

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_after_timeout(self):
        """Test circuit breaker transitions to HALF_OPEN after timeout"""
        breaker = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            success_threshold=3,
            timeout=0.1,
        )

        for _ in range(3):
            breaker.record_failure()

        assert breaker.get_state() == "OPEN"

        await asyncio.sleep(0.15)

        # Should transition to HALF_OPEN after timeout when can_execute() is called
        assert breaker.can_execute() is True
        assert breaker.get_state() == "HALF_OPEN"

    @pytest.mark.asyncio
    async def test_circuit_breaker_execute_success(self):
        """Test circuit breaker execute successful operation"""
        breaker = CircuitBreaker(
            service_name="test_service",
            failure_threshold=3,
            success_threshold=3,
            timeout=60,
        )

        operation = AsyncMock(return_value="success")

        result = await breaker.execute(operation)

        assert result == "success"
        assert operation.call_count == 1


class TestRetryFunction:
    """Test retry function"""

    @pytest.mark.asyncio
    async def test_retry_decorator_success_on_first_attempt(self):
        """Test retry decorator succeeds on first attempt"""
        call_count = 0

        @retry(operation_name="test_operation")
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await test_func()

        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_decorator_success_on_second_attempt(self):
        """Test retry decorator succeeds on second attempt"""
        call_count = 0

        @retry(operation_name="test_operation")
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Failed")
            return "success"

        result = await test_func()

        assert result == "success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_decorator_exhausts_attempts(self):
        """Test retry decorator exhausts all attempts"""
        call_count = 0

        @retry(operation_name="test_operation", policy=RetryPolicy(max_attempts=2))
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Failed")

        with pytest.raises(RetryError):
            await test_func()

        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_async_operation_success_on_first_attempt(self):
        """Test retry_async_operation succeeds on first attempt"""
        operation = AsyncMock(return_value="success")

        result = await retry_async_operation(
            operation,
            operation_name="test_operation",
        )

        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_async_operation_success_on_second_attempt(self):
        """Test retry_async_operation succeeds on second attempt"""
        operation = AsyncMock(side_effect=[ConnectionError("Failed"), "success"])

        result = await retry_async_operation(
            operation,
            operation_name="test_operation",
        )

        assert result == "success"
        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_async_operation_exhausts_attempts(self):
        """Test retry_async_operation exhausts all attempts"""
        operation = AsyncMock(side_effect=ConnectionError("Failed"))

        with pytest.raises(RetryError):
            await retry_async_operation(
                operation,
                operation_name="test_operation",
                policy=RetryPolicy(max_attempts=2),
            )

        assert operation.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_decorator_non_transient_error(self):
        """Test retry decorator doesn't retry non-transient errors"""
        call_count = 0

        @retry(operation_name="test_operation")
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ValueError("Invalid")

        with pytest.raises(ValueError):
            await test_func()

        assert call_count == 1


class TestRetryError:
    """Test RetryError exception"""

    def test_retry_error_creation(self):
        """Test RetryError creation"""
        error = RetryError(
            operation="test_operation",
            attempts=3,
            last_exception=ConnectionError("Failed"),
            total_delay=5.0,
        )

        assert error.operation == "test_operation"
        assert error.attempts == 3
        assert error.total_delay == 5.0
        assert "test_operation" in str(error)
        assert "3 attempts" in str(error)


class TestWithCircuitBreaker:
    """Test with_circuit_breaker decorator"""

    @pytest.mark.asyncio
    async def test_with_circuit_breaker_success(self):
        """Test with_circuit_breaker decorator success"""
        operation = AsyncMock(return_value="success")

        @with_circuit_breaker(
            service_name="test_service",
            failure_threshold=3,
            success_threshold=3,
            timeout=60,
        )
        async def test_func(*args, **kwargs):
            return await operation(*args, **kwargs)

        result = await test_func()

        assert result == "success"
        assert operation.call_count == 1

    @pytest.mark.asyncio
    async def test_with_circuit_breaker_opens(self):
        """Test with_circuit_breaker opens circuit after threshold"""
        call_count = 0

        @with_circuit_breaker(
            service_name="test_service",
            failure_threshold=2,
            success_threshold=3,
            timeout=60,
        )
        async def test_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Failed")

        with pytest.raises(ConnectionError):
            await test_func()

        with pytest.raises(ConnectionError):
            await test_func()

        assert call_count == 2
