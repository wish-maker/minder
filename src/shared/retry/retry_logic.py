"""
Retry logic with exponential backoff for Minder services.
Handles transient failures gracefully.
"""

import asyncio
import logging
from functools import wraps
from typing import Any, Callable, Optional, Tuple, Type

import aiohttp
from asyncpg import PostgresError

from .retry_strategy import RetryStrategy, RetryPolicy
from .circuit_breaker import CircuitBreaker, CircuitBreakerError

logger = logging.getLogger("minder.retry_logic")


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


def retry(
    operation_name: Optional[str] = None,
    policy: Optional[RetryPolicy] = None,
    exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    on_retry_callback: Optional[Callable[[Exception, int, float], None]] = None,
):
    """
    Decorator to add retry logic to async functions.

    Args:
        operation_name: Name of the operation (defaults to function name)
        policy: Retry policy to use (defaults to exponential backoff)
        exceptions: Tuple of exception types to retry on
        on_retry_callback: Callback function called on each retry

    Returns:
        Decorated function with retry logic
    """

    if policy is None:
        policy = RetryPolicy(strategy=RetryStrategy.EXPONENTIAL, max_attempts=3)

    if exceptions is None:
        # Default exceptions to retry on
        exceptions = (
            aiohttp.ClientError,
            PostgresError,
            ConnectionError,
            TimeoutError,
        )

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            name = operation_name or func.__name__
            last_exception = None
            total_delay = 0.0

            for attempt in range(1, policy.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    # Check if this was the last attempt
                    if attempt == policy.max_attempts:
                        logger.error(
                            f"Retry failed after {attempt} attempts for '{name}': {str(e)}"
                        )
                        raise RetryError(name, attempt, e, total_delay)

                    # Calculate delay for next attempt
                    delay = policy.calculate_delay(attempt)
                    total_delay += delay

                    logger.warning(
                        f"Retry attempt {attempt}/{policy.max_attempts} for '{name}' "
                        f"after {delay:.2f}s: {str(e)}"
                    )

                    # Call on_retry callback if provided
                    if on_retry_callback:
                        try:
                            on_retry_callback(e, attempt, delay)
                        except Exception as callback_error:
                            logger.error(
                                f"Error in on_retry_callback for '{name}': "
                                f"{str(callback_error)}"
                            )

                    # Wait before retrying
                    await asyncio.sleep(delay)

                except Exception as e:
                    # Re-raise non-retryable exceptions immediately
                    logger.error(
                        f"Non-retryable exception in '{name}': {str(e)}"
                    )
                    raise

        return wrapper

    return decorator


async def retry_async_operation(
    operation: Callable[..., Any],
    *args,
    operation_name: Optional[str] = None,
    policy: Optional[RetryPolicy] = None,
    exceptions: Optional[Tuple[Type[Exception], ...]] = None,
    **kwargs,
) -> Any:
    """
    Retry an async operation with backoff.

    Args:
        operation: Async callable to retry
        *args: Positional arguments for operation
        operation_name: Name of the operation
        policy: Retry policy to use
        exceptions: Tuple of exception types to retry on
        **kwargs: Keyword arguments for operation

    Returns:
        Result of operation

    Raises:
        RetryError: If all retry attempts fail
    """
    if policy is None:
        policy = RetryPolicy(strategy=RetryStrategy.EXPONENTIAL, max_attempts=3)

    if exceptions is None:
        exceptions = (
            aiohttp.ClientError,
            PostgresError,
            ConnectionError,
            TimeoutError,
        )

    name = operation_name or operation.__name__
    last_exception = None
    total_delay = 0.0

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await operation(*args, **kwargs)

        except exceptions as e:
            last_exception = e

            # Check if this was the last attempt
            if attempt == policy.max_attempts:
                logger.error(
                    f"Retry failed after {attempt} attempts for '{name}': {str(e)}"
                )
                raise RetryError(name, attempt, e, total_delay)

            # Calculate delay for next attempt
            delay = policy.calculate_delay(attempt)
            total_delay += delay

            logger.warning(
                f"Retry attempt {attempt}/{policy.max_attempts} for '{name}' "
                f"after {delay:.2f}s: {str(e)}"
            )

            # Wait before retrying
            await asyncio.sleep(delay)

        except Exception as e:
            # Re-raise non-retryable exceptions immediately
            logger.error(f"Non-retryable exception in '{name}': {str(e)}")
            raise


def with_circuit_breaker(
    service_name: str,
    failure_threshold: int = 5,
    success_threshold: int = 3,
    timeout: float = 60.0,
):
    """
    Decorator to add circuit breaker to async functions.

    Args:
        service_name: Name of the service
        failure_threshold: Number of failures before opening circuit
        success_threshold: Number of successes to close circuit
        timeout: How long to keep circuit open

    Returns:
        Decorated function with circuit breaker
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        circuit_breaker = CircuitBreaker(
            service_name=service_name,
            failure_threshold=failure_threshold,
            success_threshold=success_threshold,
            timeout=timeout,
        )

        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            return await circuit_breaker.execute(func, *args, **kwargs)

        return wrapper

    return decorator
