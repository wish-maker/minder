"""
Circuit breaker implementation for Minder.
Prevents cascading failures by failing fast when service is unhealthy.
"""

import asyncio
import logging
from typing import Optional
import time


logger = logging.getLogger("minder.circuit_breaker")


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
            logger.info(
                f"Circuit breaker for {self.service_name}: Success in HALF_OPEN "
                f"({self.success_count}/{self.success_threshold})"
            )

            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"
                self.success_count = 0
                self.failure_count = 0
                logger.info(f"Circuit breaker for {self.service_name}: CLOSED")
        else:
            # Reset failure count on success in CLOSED state
            self.failure_count = 0

    def record_failure(self):
        """Record a failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == "OPEN":
            logger.warning(
                f"Circuit breaker for {self.service_name}: Failed while OPEN "
                f"(failure_count={self.failure_count})"
            )
        elif self.state == "HALF_OPEN":
            logger.warning(
                f"Circuit breaker for {self.service_name}: Failed in HALF_OPEN, "
                f"reopening"
            )
            self.state = "OPEN"
            self.success_count = 0
        elif self.failure_count >= self.failure_threshold:
            logger.warning(
                f"Circuit breaker for {self.service_name}: Opening "
                f"(failure_count={self.failure_count})"
            )
            self.state = "OPEN"
            self.success_count = 0

    def can_execute(self) -> bool:
        """Check if operation can be executed (circuit is not open)"""
        if self.state == "CLOSED":
            return True
        elif self.state == "OPEN":
            # Check if timeout has elapsed
            if time.time() - self.last_failure_time >= self.timeout:
                logger.info(f"Circuit breaker for {self.service_name}: HALF_OPEN")
                self.state = "HALF_OPEN"
                self.success_count = 0
                return True
            else:
                return False
        else:  # HALF_OPEN
            return True

    async def execute(self, operation: callable, *args, **kwargs):
        """
        Execute operation with circuit breaker protection.

        Args:
            operation: Callable to execute
            *args: Positional arguments for operation
            **kwargs: Keyword arguments for operation

        Returns:
            Result of operation

        Raises:
            CircuitBreakerError: If circuit is open
            Exception: Re-raises any exception from operation
        """
        if not self.can_execute():
            raise CircuitBreakerError(self.service_name)

        try:
            result = await operation(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    def reset(self):
        """Reset circuit breaker to closed state"""
        self.state = "CLOSED"
        self.failure_count = 0
        self.success_count = 0
        logger.info(f"Circuit breaker for {self.service_name}: Reset to CLOSED")

    def get_state(self) -> str:
        """Get current circuit breaker state"""
        return self.state

    def get_stats(self) -> dict:
        """Get circuit breaker statistics"""
        return {
            "service": self.service_name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
        }
