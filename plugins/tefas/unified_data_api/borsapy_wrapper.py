"""
BorsapyWrapper - borsapy library wrapper with caching and error handling

Provides methods to access borsapy's advanced features including:
- Fund basic info and metadata
- Risk metrics (Sharpe, Sortino, max drawdown)
- Asset allocation data
- Withholding tax rates
- Fund screening and comparison
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

try:
    import borsapy as bp

    BORSAPY_AVAILABLE = True
except ImportError:
    BORSAPY_AVAILABLE = False
    logging.warning("borsapy not installed. Install with: pip install borsapy")

logger = logging.getLogger("minder.tefas.borsapy_wrapper")


class BorsapyWrapper:
    """
    borsapy library wrapper with caching and error handling

    Provides methods to access borsapy's advanced features including:
    - Fund basic info and metadata
    - Risk metrics (Sharpe, Sortino, max drawdown)
    - Asset allocation data
    - Withholding tax rates
    - Fund screening and comparison
    """

    def __init__(self, cache_ttl: int = 3600):
        """
        Initialize Borsapy wrapper

        Args:
            cache_ttl: Cache time-to-live in seconds (default: 1 hour)
        """
        if not BORSAPY_AVAILABLE:
            raise ImportError("borsapy is not installed. Install with: pip install borsapy")

        self.cache = {}
        self.cache_ttl = cache_ttl
        self.cache_stats = {"hits": 0, "misses": 0, "errors": 0}

        logger.info("✅ BorsapyWrapper initialized (cache TTL: %ds)", cache_ttl)

    def get_fund_info(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get fund basic information

        Args:
            fund_code: TEFAS fund code (e.g., "AAK")

        Returns:
            Dict with fund info or None if failed
        """
        cache_key = f"fund_info:{fund_code}"

        if self._is_cached(cache_key):
            self.cache_stats["hits"] += 1
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            data = fon.info

            if data:
                self._cache_set(cache_key, data)
                self.cache_stats["misses"] += 1
                logger.debug(f"Borsapy: Fetched info for {fund_code}")
                return data

        except Exception as e:
            self.cache_stats["errors"] += 1
            logger.error(f"Borsapy: Fund info error for {fund_code}: {e}")

        return None

    def get_fund_metadata(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get complete fund metadata

        Args:
            fund_code: TEFAS fund code

        Returns:
            Dict with complete metadata or None
        """
        cache_key = f"fund_metadata:{fund_code}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)

            data = {
                "code": fund_code,
                "title": fon.info.get("longName") or fon.info.get("title", ""),
                "category": fon.info.get("category"),
                "isin": fon.isin if hasattr(fon, "isin") else None,
                "management_fee": (fon.management_fee if hasattr(fon, "management_fee") else None),
                "inception_date": fon.info.get("inceptionDate"),
                "fund_type": self._detect_fund_type(fund_code),
            }

            self._cache_set(cache_key, data)
            return data

        except Exception as e:
            logger.error(f"Borsapy: Fund metadata error for {fund_code}: {e}")

        return None

    def get_risk_metrics(self, fund_code: str, period: str = "1y") -> Optional[Dict[str, Any]]:
        """
        Get fund risk metrics

        Args:
            fund_code: TEFAS fund code
            period: Calculation period ('1y', '3y', '5y')

        Returns:
            Dict with risk metrics or None if failed
        """
        cache_key = f"risk_metrics:{fund_code}:{period}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            metrics = fon.risk_metrics(period=period)

            if metrics:
                self._cache_set(cache_key, metrics)
                logger.debug(f"Borsapy: Risk metrics for {fund_code} ({period})")
                return metrics

        except Exception as e:
            logger.error(f"Borsapy: Risk metrics error for {fund_code}: {e}")

        return None

    def get_allocation(self, fund_code: str) -> Optional[pd.DataFrame]:
        """
        Get fund asset allocation

        Args:
            fund_code: TEFAS fund code

        Returns:
            DataFrame with allocation data or None if failed
        """
        cache_key = f"allocation:{fund_code}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            allocation = fon.allocation

            if allocation is not None and not allocation.empty:
                self._cache_set(cache_key, allocation)
                logger.debug(f"Borsapy: Allocation for {fund_code} ({len(allocation)} assets)")
                return allocation

        except Exception as e:
            logger.error(f"Borsapy: Allocation error for {fund_code}: {e}")

        return None

    def get_allocation_history(self, fund_code: str, period: str = "3ay") -> Optional[pd.DataFrame]:
        """
        Get historical asset allocation

        Args:
            fund_code: TEFAS fund code
            period: Period for history ('1mo', '3ay', 'max')

        Returns:
            DataFrame with historical allocation or None if failed
        """
        cache_key = f"allocation_history:{fund_code}:{period}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            history = fon.allocation_history(period=period)

            if history is not None and not history.empty:
                self._cache_set(cache_key, history)
                logger.debug(f"Borsapy: Allocation history for {fund_code} ({len(history)} records)")
                return history

        except Exception as e:
            logger.error(f"Borsapy: Allocation history error for {fund_code}: {e}")

        return None

    def get_tax_rate(self, fund_code: str, date: str) -> Optional[float]:
        """
        Get withholding tax rate for a fund

        Args:
            fund_code: TEFAS fund code
            date: Date string (YYYY-MM-DD)

        Returns:
            Tax rate as decimal (0.15 = 15%) or None if failed
        """
        cache_key = f"tax_rate:{fund_code}:{date}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            rate = fon.withholding_tax_rate(date)

            self._cache_set(cache_key, rate)
            logger.debug(f"Borsapy: Tax rate for {fund_code} on {date}: {rate}")
            return rate

        except Exception as e:
            logger.error(f"Borsapy: Tax rate error for {fund_code}: {e}")

        return None

    def get_tax_category(self, fund_code: str) -> Optional[str]:
        """
        Get fund tax category

        Args:
            fund_code: TEFAS fund code

        Returns:
            Tax category string or None if failed
        """
        try:
            fon = bp.Fund(fund_code)
            return fon.tax_category if hasattr(fon, "tax_category") else None
        except Exception as e:
            logger.error(f"Borsapy: Tax category error for {fund_code}: {e}")

        return None

    def screen_funds(self, **criteria) -> Optional[pd.DataFrame]:
        """
        Screen funds by criteria

        Args:
            **criteria: Screening criteria (e.g., min_return_1y=50)

        Returns:
            DataFrame with matching funds or None if failed
        """
        try:
            results = bp.screen_funds(**criteria)
            num_results = len(results) if results is not None else 0
            logger.info(f"Borsapy: Screened funds with criteria {criteria}: {num_results} results")
            return results
        except Exception as e:
            logger.error(f"Borsapy: Screening error: {e}")
            return None

    def compare_funds(self, fund_codes: List[str]) -> Optional[Dict[str, Any]]:
        """
        Compare multiple funds

        Args:
            fund_codes: List of fund codes to compare

        Returns:
            Dict with comparison results or None if failed
        """
        if len(fund_codes) > 10:
            logger.warning(f"Borsapy: Comparing >10 funds may be slow. Got {len(fund_codes)} funds")

        try:
            comparison = bp.compare_funds(fund_codes)
            logger.info(f"Borsapy: Compared {len(fund_codes)} funds")
            return comparison
        except Exception as e:
            logger.error(f"Borsapy: Comparison error: {e}")
            return None

    def get_performance(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get fund performance metrics

        Args:
            fund_code: TEFAS fund code

        Returns:
            Dict with performance metrics or None if failed
        """
        cache_key = f"performance:{fund_code}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            perf = fon.performance

            if perf:
                self._cache_set(cache_key, perf)
                return perf

        except Exception as e:
            logger.error(f"Borsapy: Performance error for {fund_code}: {e}")

        return None

    def get_fund_history(self, fund_code: str, period: str = "1mo") -> Optional[pd.DataFrame]:
        """
        Get fund price history

        Args:
            fund_code: TEFAS fund code
            period: Period for history ('1d', '1w', '1mo', '3mo', '1y', 'max')

        Returns:
            DataFrame with OHLCV data or None if failed
        """
        cache_key = f"history:{fund_code}:{period}"

        if self._is_cached(cache_key):
            return self.cache[cache_key]["data"]

        try:
            fon = bp.Fund(fund_code)
            history = fon.history(period=period)

            if history is not None and not history.empty:
                self._cache_set(cache_key, history)
                logger.debug(f"Borsapy: History for {fund_code} ({period}): {len(history)} records")
                return history

        except Exception as e:
            logger.error(f"Borsapy: History error for {fund_code}: {e}")

        return None

    def _is_cached(self, key: str) -> bool:
        """Check if cache key exists and is valid"""
        if key not in self.cache:
            return False

        cached_time = self.cache[key]["time"]
        age = (datetime.now() - cached_time).total_seconds()

        return age < self.cache_ttl

    def _cache_set(self, key: str, data: Any):
        """Set cache with timestamp"""
        self.cache[key] = {"data": data, "time": datetime.now()}

    def _detect_fund_type(self, fund_code: str) -> str:
        """Detect fund type from fund code"""
        if fund_code.startswith("E"):
            return "EMK"
        elif fund_code.startswith("B"):
            return "BYF"
        else:
            return "YAT"

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_requests = self.cache_stats["hits"] + self.cache_stats["misses"]
        hit_rate = self.cache_stats["hits"] / total_requests if total_requests > 0 else 0

        return {
            "hits": self.cache_stats["hits"],
            "misses": self.cache_stats["misses"],
            "errors": self.cache_stats["errors"],
            "hit_rate": round(hit_rate * 100, 2),  # percentage
            "cache_size": len(self.cache),
        }

    def clear_cache(self):
        """Clear all cache"""
        self.cache.clear()
        logger.info("BorsapyWrapper: Cache cleared")
