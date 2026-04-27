"""
Retry logic with exponential backoff for Minder services.
Handles transient failures gracefully.
"""

import asyncio
import logging
from enum import Enum
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

import aiohttp
from asyncpg import PostgresError

logger = logging.getLogger("minder.retry_logic")


class RetryStrategy(Enum):
    """Retry strategies"""

    # Exponential backoff: 1s, 2s, 4s, 8s, ...
    EXPONENTIAL = "exponential"

    # Linear backoff: 1s, 2s, 3s, 4s, ...
    LINEAR = "linear"

    # Fixed delay: 1s, 1s, 1s, 1s, ...
    FIXED = "fixed"

    # No retry
    NONE = "none"


class RetryError(Exception):
    """Raised when all retry attempts are exhausted"""

    def __init__(
        self, operation: str, attempts: int, last_exception: Exception, total_delay: float
    ):
        self.operation = operation
        self.attempts = attempts
        self.last_exception = last_exception
        self.total_delay = total_delay
        message = (
            f"Retry failed after {attempts} attempts for operation '{operation}'. "
            f"Total delay: {total_delay:.2f}s. Last error: {str(last_exception)}"
        )
        super().__init__(message)


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open"""

    def __init__(self, service: str):
        self.service = service
        message = f"Circuit breaker is OPEN for service: {service}"
        super().__init__(message)


class CircuitBreaker:
    """
    Circuit breaker for external services.
    Prevents cascading failures by failing fast when service is unhealthy.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: float = 60.0,
    ):
        """
        Initialize circuit breaker.

        Args:
            service_name: Name of the service being protected
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes needed to close circuit
            timeout: How long to keep circuit open (seconds)
        """
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout

        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN

        logger.info(
            f"Circuit breaker initialized for {service_name}: "
            f"failure_threshold={failure_threshold}, timeout={timeout}s"
        )

    def record_success(self):
        """Record a successful operation"""
        if self.state == "OPEN":
            self.success_count += 1

            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"
                self.success_count = 0
                self.failure_count = 0
                logger.info(f"Circuit breaker CLOSED for {self.service_name}")
        else:
            self.failure_count = 0

    def record_failure(self):
        """Record a failed operation"""
        self.failure_count += 1
        self.last_failure_time = asyncio.get_event_loop().time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Circuit breaker OPENED for {self.service_name} "
                f"(failures: {self.failure_count})"
            )

    def can_attempt(self) -> bool:
        """
        Check if operation can be attempted.

        Returns:
            True if circuit is closed or half-open, False if open
        """
        if self.state == "CLOSED":
            return True

        if self.state == "OPEN":
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_failure_time >= self.timeout:
                self.state = "HALF_OPEN"
                self.success_count = 0
                logger.info(f"Circuit breaker HALF-OPEN for {self.service_name}")
                return True
            return False

        if self.state == "HALF_OPEN":
            return True

        return False

    async def __aenter__(self):
        """Enter circuit breaker context"""
        if not self.can_attempt():
            raise CircuitBreakerError(self.service_name)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit circuit breaker context"""
        if exc_type is None:
            self.record_success()
        else:
            self.record_failure()


def calculate_delay(
    attempt: int,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
) -> float:
    """
    Calculate delay for retry attempt.

    Args:
        attempt: Attempt number (1-based)
        strategy: Retry strategy
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds

    Returns:
        Delay in seconds
    """
    if strategy == RetryStrategy.EXPONENTIAL:
        delay = base_delay * (2 ** (attempt - 1))
    elif strategy == RetryStrategy.LINEAR:
        delay = base_delay * attempt
    elif strategy == RetryStrategy.FIXED:
        delay = base_delay
    else:
        delay = 0.0

    # Apply jitter (randomize delay by ±20%)
    import random

    jitter = random.uniform(0.8, 1.2)
    delay *= jitter

    # Cap at max delay
    return float(min(delay, max_delay))


def is_transient_error(exception: Exception) -> bool:
    """
    Check if exception is a transient error that can be retried.

    Args:
        exception: Exception to check

    Returns:
        True if error is transient
    """
    # Network errors
    if isinstance(exception, aiohttp.ClientError):
        return True

    # Database connection errors
    if isinstance(exception, (ConnectionError, TimeoutError)):
        return True

    # Specific PostgreSQL errors that are transient
    if isinstance(exception, PostgresError):
        # Check error code (transient: 40xxx, 53xxx)
        code = getattr(exception, "sqlstate", None)
        if code:
            # 40xxx: Transaction rollback
            # 53xxx: Insufficient resources
            return bool(code.startswith("40") or code.startswith("53"))

    return False


async def retry(
    operation: Callable,
    operation_name: str,
    max_attempts: int = 3,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    circuit_breaker: Optional[CircuitBreaker] = None,
) -> Any:
    """
    Execute operation with retry logic.

    Args:
        operation: Async callable to execute
        operation_name: Description of operation
        max_attempts: Maximum number of retry attempts
        strategy: Retry strategy
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        retry_on: Tuple of exception types to retry on
        circuit_breaker: Optional circuit breaker

    Returns:
        Result of operation

    Raises:
        RetryError: When all attempts are exhausted
        CircuitBreakerError: When circuit breaker is open

    Example:
        async def my_function():
            # Some operation
            pass

        result = await retry(
            my_function,
            "database operation",
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL
        )
    """
    if strategy == RetryStrategy.NONE:
        return await operation()

    total_delay = 0.0

    for attempt in range(1, max_attempts + 1):
        try:
            # Check circuit breaker
            if circuit_breaker:
                async with circuit_breaker:
                    result = await operation()
            else:
                result = await operation()

            # Success
            if attempt > 1:
                logger.info(
                    f"Operation '{operation_name}' succeeded on attempt {attempt}/{max_attempts}"
                )

            return result

        except Exception as e:
            # Check if exception is retryable
            if retry_on:
                if not isinstance(e, retry_on):
                    # Not a retryable exception, re-raise immediately
                    raise

            if not is_transient_error(e):
                # Not a transient error, re-raise immediately
                raise

            # Last attempt, raise
            if attempt == max_attempts:
                logger.error(
                    f"Operation '{operation_name}' failed after {max_attempts} attempts. "
                    f"Last error: {str(e)}"
                )
                raise RetryError(
                    operation=operation_name,
                    attempts=max_attempts,
                    last_exception=e,
                    total_delay=total_delay,
                )

            # Calculate delay
            delay = calculate_delay(attempt, strategy, base_delay, max_delay)
            total_delay += delay

            # Log retry
            logger.warning(
                f"Operation '{operation_name}' failed on attempt {attempt}/{max_attempts}. "
                f"Retrying in {delay:.2f}s. Error: {str(e)}"
            )

            # Wait before retry
            await asyncio.sleep(delay)


def retry_decorator(
    max_attempts: int = 3,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retry_on: Optional[Tuple[Type[Exception], ...]] = None,
    circuit_breaker_name: Optional[str] = None,
):
    """
    Decorator for adding retry logic to functions.

    Args:
        max_attempts: Maximum retry attempts
        strategy: Retry strategy
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        retry_on: Exception types to retry on
        circuit_breaker_name: Name for circuit breaker (optional)

    Example:
        @retry_decorator(max_attempts=3, strategy=RetryStrategy.EXPONENTIAL)
        async def my_function():
            # Some operation
            pass
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            operation_name = f"{func.__module__}.{func.__name__}"

            # Create circuit breaker if specified
            circuit_breaker = None
            if circuit_breaker_name:
                # Store circuit breakers in function's attribute
                if not hasattr(wrapper, "_circuit_breakers"):
                    wrapper._circuit_breakers = {}

                if circuit_breaker_name not in wrapper._circuit_breakers:
                    wrapper._circuit_breakers[circuit_breaker_name] = CircuitBreaker(
                        circuit_breaker_name
                    )

                circuit_breaker = wrapper._circuit_breakers[circuit_breaker_name]

            return await retry(
                operation=lambda: func(*args, **kwargs),
                operation_name=operation_name,
                max_attempts=max_attempts,
                strategy=strategy,
                base_delay=base_delay,
                max_delay=max_delay,
                retry_on=retry_on,
                circuit_breaker=circuit_breaker,
            )

        return wrapper

    return decorator


# Retry presets for common use cases


class RetryPresets:
    """Common retry configurations"""

    # Database operations
    DATABASE = {
        "max_attempts": 3,
        "strategy": RetryStrategy.EXPONENTIAL,
        "base_delay": 0.5,
        "max_delay": 5.0,
        "retry_on": (ConnectionError, TimeoutError, PostgresError),
    }

    # External HTTP API calls
    HTTP_REQUEST = {
        "max_attempts": 3,
        "strategy": RetryStrategy.EXPONENTIAL,
        "base_delay": 1.0,
        "max_delay": 10.0,
        "retry_on": (aiohttp.ClientError, TimeoutError, ConnectionError),
    }

    # Heavy operations
    HEAVY_OPERATION = {
        "max_attempts": 2,
        "strategy": RetryStrategy.LINEAR,
        "base_delay": 2.0,
        "max_delay": 30.0,
    }

    # Fast operations
    FAST_OPERATION = {
        "max_attempts": 5,
        "strategy": RetryStrategy.EXPONENTIAL,
        "base_delay": 0.1,
        "max_delay": 2.0,
    }

    # No retry
    NO_RETRY = {"max_attempts": 1, "strategy": RetryStrategy.NONE}


def get_retry_preset(preset_name: str) -> dict:
    """
    Get retry configuration preset.

    Args:
        preset_name: Name of preset

    Returns:
        Dictionary with retry configuration

    Available presets:
        - database
        - http_request
        - heavy_operation
        - fast_operation
        - no_retry
    """
    presets = {
        "database": RetryPresets.DATABASE,
        "http_request": RetryPresets.HTTP_REQUEST,
        "heavy_operation": RetryPresets.HEAVY_OPERATION,
        "fast_operation": RetryPresets.FAST_OPERATION,
        "no_retry": RetryPresets.NO_RETRY,
    }

    return presets.get(preset_name.lower(), RetryPresets.HTTP_REQUEST)


# Context manager for retry


class RetryContext:
    """Context manager for retry operations"""

    def __init__(self, operation_name: str, **retry_kwargs):
        self.operation_name = operation_name
        self.retry_kwargs = retry_kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False


# Fallback mechanism


class FallbackHandler:
    """Handle fallback operations when primary fails"""

    def __init__(self, primary_func: Callable, fallback_func: Callable):
        """
        Initialize fallback handler.

        Args:
            primary_func: Primary function to try first
            fallback_func: Fallback function to use if primary fails
        """
        self.primary_func = primary_func
        self.fallback_func = fallback_func

    async def execute(self, *args, **kwargs) -> Any:
        """
        Execute primary function, fallback on failure.

        Args:
            *args: Arguments to pass to functions
            **kwargs: Keyword arguments to pass to functions

        Returns:
            Result from primary or fallback function
        """
        try:
            return await self.primary_func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Primary function failed: {str(e)}. Using fallback.")
            return await self.fallback_func(*args, **kwargs)


def with_fallback(fallback_func: Callable):
    """
    Decorator to add fallback function.

    Args:
        fallback_func: Fallback function

    Example:
        async def fallback():
            return "fallback_result"

        @with_fallback(fallback)
        async def primary():
            # Some operation that might fail
            pass
    """

    def decorator(primary_func: Callable) -> Callable:
        @wraps(primary_func)
        async def wrapper(*args, **kwargs):
            handler = FallbackHandler(primary_func, fallback_func)
            return await handler.execute(*args, **kwargs)

        return wrapper

    return decorator
