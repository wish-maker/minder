"""
Retry strategies and constants for Minder.
Defines retry strategies and retry policies.
"""

import asyncio
from enum import Enum


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


class RetryPolicy:
    """
    Retry policy configuration.
    """

    def __init__(
        self,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        backoff_multiplier: float = 2.0
    ):
        """
        Initialize retry policy.

        Args:
            strategy: Retry strategy to use
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay in seconds
            max_delay: Maximum delay in seconds
            backoff_multiplier: Multiplier for exponential backoff
        """
        self.strategy = strategy
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for the given attempt.

        Args:
            attempt: Current attempt number (1-indexed)

        Returns:
            Delay in seconds
        """
        if self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (self.backoff_multiplier ** (attempt - 1))
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * attempt
        elif self.strategy == RetryStrategy.FIXED:
            delay = self.base_delay
        else:
            delay = 0

        return min(delay, self.max_delay)
