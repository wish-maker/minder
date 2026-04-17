"""
Unified Data API - TEFAS data source abstraction layer
Supports borsapy and tefas-crawler with automatic fallback mechanism

This module provides a unified interface for accessing TEFAS data from multiple sources
with automatic fallback, caching, and error handling.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pandas as pd

# Try to import borsapy
try:
    import borsapy as bp

    BORSAPY_AVAILABLE = True
except ImportError:
    BORSAPY_AVAILABLE = False
    logging.warning("borsapy not installed. Install with: pip install borsapy")

# Try to import tefas-crawler
try:
    from tefas import Crawler

    TEFAS_CRAWLER_AVAILABLE = True
except ImportError:
    TEFAS_CRAWLER_AVAILABLE = False
    logging.warning("tefas-crawler not installed. Install with: pip install tefas-crawler")

logger = logging.getLogger("minder.tefas.api")


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
                "management_fee": fon.management_fee if hasattr(fon, "management_fee") else None,
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


class TefasCrawlerWrapper:
    """
    tefas-crawler wrapper for fallback support

    Provides basic fund data collection using tefas-crawler package
    """

    def __init__(self):
        """Initialize TEFAS crawler wrapper"""
        if not TEFAS_CRAWLER_AVAILABLE:
            raise ImportError("tefas-crawler is not installed. Install with: pip install tefas-crawler")

        self.crawler = Crawler()
        logger.info("✅ TefasCrawlerWrapper initialized")

    def get_fund_history(
        self, fund_code: str, start: str, end: str, fund_type: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """
        Get historical price data from tefas-crawler

        Args:
            fund_code: TEFAS fund code
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)
            fund_type: Fund type (YAT, EMK, BYF) - auto-detected if None

        Returns:
            DataFrame with price history or None if failed
        """
        try:
            # Auto-detect fund type if not provided
            if fund_type is None:
                if fund_code.startswith("E"):
                    fund_type = "EMK"
                elif fund_code.startswith("B"):
                    fund_type = "BYF"
                else:
                    fund_type = "YAT"

            data = self.crawler.fetch(start=start, end=end, kind=fund_type)

            if data is not None and not data.empty:
                logger.debug(f"TefasCrawler: Fetched history for {fund_code} ({len(data)} records)")
                return data

        except Exception as e:
            logger.error(f"TefasCrawler: History error for {fund_code}: {e}")

        return None

    def discover_funds(self, date: str, fund_types: List[str] = None) -> Dict[str, set]:
        """
        Discover all available funds for given date and types

        Args:
            date: Date to discover funds (YYYY-MM-DD)
            fund_types: List of fund types (YAT, EMK, BYF)

        Returns:
            Dict mapping fund types to sets of fund codes
        """
        if fund_types is None:
            fund_types = ["YAT", "EMK", "BYF"]

        discovered = {ft: set() for ft in fund_types}

        for fund_type in fund_types:
            try:
                data = self.crawler.fetch(start=date, end=date, kind=fund_type)

                if data is not None and not data.empty:
                    fund_codes = set(data["code"].unique())
                    discovered[fund_type] = fund_codes
                    logger.debug(f"TefasCrawler: Discovered {len(fund_codes)} {fund_type} funds")

            except Exception as e:
                logger.error(f"TefasCrawler: Discovery error for {fund_type}: {e}")

        return discovered


class UnifiedDataAPI:
    """
    Unified data API with automatic fallback mechanism

    Provides a single interface to TEFAS data that:
    1. Tries borsapy first (primary source with advanced features)
    2. Falls back to tefas-crawler if borsapy fails
    3. Handles caching, error recovery, and graceful degradation
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize unified data API

        Args:
            config: Configuration dict with data_sources and cache settings
        """
        self.config = config
        self.cache_ttl = config.get("cache", {}).get("ttl", 3600)
        self.primary_source = config.get("data_sources", {}).get("primary", "borsapy")
        self.fallback_enabled = config.get("data_sources", {}).get("auto_switch", True)

        # Initialize wrappers
        self.borsapy = None
        self.tefas_crawler = None

        # Initialize primary source
        if self.primary_source == "borsapy":
            if BORSAPY_AVAILABLE:
                try:
                    self.borsapy = BorsapyWrapper(cache_ttl=self.cache_ttl)
                    logger.info("📊 UnifiedDataAPI: Primary source = borsapy")
                except Exception as e:
                    logger.warning(f"Failed to initialize borsapy: {e}")

        # Initialize fallback
        if TEFAS_CRAWLER_AVAILABLE:
            try:
                self.tefas_crawler = TefasCrawlerWrapper()
                logger.info("🔄 UnifiedDataAPI: Fallback source = tefas-crawler")
            except Exception as e:
                logger.warning(f"Failed to initialize tefas-crawler: {e}")

        # Check if at least one source is available
        if self.borsapy is None and self.tefas_crawler is None:
            raise RuntimeError("Neither borsapy nor tefas-crawler is available!")

        fallback_status = "enabled" if self.fallback_enabled else "disabled"
        logger.info(f"✅ UnifiedDataAPI initialized (primary: {self.primary_source}, fallback: {fallback_status})")

    def get_fund_info(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get fund basic info with automatic fallback

        Strategy:
        1. Try borsapy if available
        2. Fall back to tefas-crawler if enabled
        3. Return None if both fail

        Args:
            fund_code: TEFAS fund code

        Returns:
            Dict with fund info or None if both sources fail
        """
        # Try primary source first
        if self.primary_source == "borsapy" and self.borsapy:
            data = self.borsapy.get_fund_info(fund_code)
            if data:
                return data

            # Fallback to tefas-crawler
            if self.fallback_enabled and self.tefas_crawler:
                logger.warning(f"Borsapy failed for {fund_code}, using tefas-crawler fallback")
                return self._get_basic_info_from_crawler(fund_code)

        # Try tefas-crawler as primary
        elif self.tefas_crawler:
            return self._get_basic_info_from_crawler(fund_code)

        return None

    def _get_basic_info_from_crawler(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """
        Get basic fund info from tefas-crawler

        Args:
            fund_code: TEFAS fund code

        Returns:
            Dict with basic fund info or None
        """
        if not self.tefas_crawler:
            return None

        try:
            today = datetime.now().strftime("%Y-%m-%d")
            data = self.tefas_crawler.get_fund_history(
                fund_code=fund_code, start=today, end=today, fund_type=None  # Auto-detect
            )

            if data is not None and not data.empty:
                row = data.iloc[0]
                return {
                    "code": row.get("code"),
                    "title": row.get("title"),
                    "price": float(row.get("price", 0)) if pd.notna(row.get("price")) else None,
                    "date": row.get("date"),
                    "market_cap": float(row.get("market_cap", 0)) if pd.notna(row.get("market_cap")) else None,
                    "volume": int(row.get("volume", 0)) if pd.notna(row.get("volume")) else None,
                }

        except Exception as e:
            logger.error(f"Tefas-crawler fallback failed for {fund_code}: {e}")

        return None

    def get_fund_metadata(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """Get fund metadata (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_fund_metadata(fund_code)
        return None

    def get_risk_metrics(self, fund_code: str, period: str = "1y") -> Optional[Dict[str, Any]]:
        """Get risk metrics (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_risk_metrics(fund_code, period)
        return None

    def get_allocation(self, fund_code: str) -> Optional[pd.DataFrame]:
        """Get asset allocation (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_allocation(fund_code)
        return None

    def get_allocation_history(self, fund_code: str, period: str = "3ay") -> Optional[pd.DataFrame]:
        """Get allocation history (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_allocation_history(fund_code, period)
        return None

    def get_tax_rate(self, fund_code: str, date: str) -> Optional[float]:
        """Get withholding tax rate (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_tax_rate(fund_code, date)
        return None

    def get_tax_category(self, fund_code: str) -> Optional[str]:
        """Get tax category (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_tax_category(fund_code)
        return None

    def screen_funds(self, **criteria) -> Optional[pd.DataFrame]:
        """Screen funds by criteria (borsapy only)"""
        if self.borsapy:
            return self.borsapy.screen_funds(**criteria)
        return None

    def compare_funds(self, fund_codes: List[str]) -> Optional[Dict[str, Any]]:
        """Compare multiple funds (borsapy only)"""
        if self.borsapy:
            return self.borsapy.compare_funds(fund_codes)
        return None

    def get_performance(self, fund_code: str) -> Optional[Dict[str, Any]]:
        """Get performance metrics (borsapy only)"""
        if self.borsapy:
            return self.borsapy.get_performance(fund_code)
        return None

    def get_fund_history(self, fund_code: str, period: str = "1mo") -> Optional[pd.DataFrame]:
        """Get fund price history"""
        if self.borsapy:
            return self.borsapy.get_fund_history(fund_code, period)

        # Fallback to tefas-crawler
        if self.tefas_crawler:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)

            return self.tefas_crawler.get_fund_history(
                fund_code=fund_code, start=start_date.strftime("%Y-%m-%d"), end=end_date.strftime("%Y-%m-%d")
            )

        return None

    def discover_funds(self, date: Optional[str] = None, fund_types: Optional[List[str]] = None) -> Dict[str, set]:
        """
        Discover all available funds

        Args:
            date: Date for discovery (defaults to today)
            fund_types: Fund types to discover

        Returns:
            Dict mapping fund types to sets of fund codes
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        if fund_types is None:
            fund_types = ["YAT", "EMK", "BYF"]

        if self.tefas_crawler:
            return self.tefas_crawler.discover_funds(date, fund_types)

        return {ft: set() for ft in fund_types}

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get health status of data sources

        Returns:
            Dict with health status of each data source
        """
        status = {
            "primary_source": self.primary_source,
            "fallback_enabled": self.fallback_enabled,
            "borsapy": {
                "available": BORSAPY_AVAILABLE,
                "initialized": self.borsapy is not None,
                "cache_stats": self.borsapy.get_cache_stats() if self.borsapy else None,
            },
            "tefas_crawler": {"available": TEFAS_CRAWLER_AVAILABLE, "initialized": self.tefas_crawler is not None},
        }

        # Determine overall health
        if status["borsapy"]["initialized"]:
            status["health"] = "healthy"
        elif status["tefas_crawler"]["initialized"]:
            status["health"] = "degraded"  # Fallback only
        else:
            status["health"] = "unhealthy"

        return status

    def clear_cache(self):
        """Clear all caches"""
        if self.borsapy:
            self.borsapy.clear_cache()
        logger.info("UnifiedDataAPI: All caches cleared")
