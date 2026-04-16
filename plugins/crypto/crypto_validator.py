"""Data quality validation for crypto API responses"""
from datetime import datetime, timezone
from typing import Tuple
import logging

logger = logging.getLogger(__name__)


class PluginDataValidator:
    """Validates data quality and freshness for crypto data"""

    def validate_crypto_data(self, data: dict) -> Tuple[bool, float]:
        """
        Validate crypto data quality

        Args:
            data: Crypto data dictionary with price, timestamp, etc.

        Returns:
            tuple: (is_valid, quality_score) where score is 0.0-1.0
        """
        score = 1.0

        # Check for null values
        if data.get("price") is None:
            logger.warning("Crypto price is null")
            score -= 0.3

        # Check for stale data
        try:
            if "timestamp" in data:
                if isinstance(data["timestamp"], str):
                    timestamp = datetime.fromisoformat(data["timestamp"])
                elif isinstance(data["timestamp"], datetime):
                    timestamp = data["timestamp"]
                else:
                    logger.warning(f"Invalid timestamp type: {type(data['timestamp'])}")
                    score -= 0.3
                    return score > 0.5, max(0.0, score)

                age = (datetime.now(timezone.utc) - timestamp).total_seconds()
                if age > 300:  # 5 minutes
                    logger.warning(f"Crypto data is stale: {age}s old")
                    score -= 0.4
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid timestamp format: {e}")
            score -= 0.3

        # Check for outliers (price changed >50% in 5 min)
        if "previous_price" in data and data.get("price"):
            try:
                change = abs(data["price"] - data["previous_price"]) / data["previous_price"]
                if change > 0.5:
                    logger.warning(f"Price outlier detected: {change * 100}% change")
                    score -= 0.3
            except (ZeroDivisionError, TypeError) as e:
                logger.warning(f"Could not calculate price change: {e}")

        is_valid = score > 0.5
        return is_valid, max(0.0, score)
