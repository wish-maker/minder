"""
UnifiedDataAPI - Unified data API with automatic fallback mechanism

Provides a single interface to TEFAS data that:
1. Tries borsapy first (primary source with advanced features)
2. Falls back to tefas-crawler if borsapy fails
3. Handles caching, error recovery, and graceful degradation
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

import pandas as pd

from .borsapy_wrapper import BORSAPY_AVAILABLE, BorsapyWrapper
from .tefas_crawler_wrapper import TEFAS_CRAWLER_AVAILABLE, TefasCrawlerWrapper

logger = logging.getLogger("minder.tefas.unified_api")


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
        self.borsapy: Optional[BorsapyWrapper] = None
        self.tefas_crawler: Optional[TefasCrawlerWrapper] = None

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
                    "price": (float(row.get("price", 0)) if pd.notna(row.get("price")) else None),
                    "date": row.get("date"),
                    "market_cap": (float(row.get("market_cap", 0)) if pd.notna(row.get("market_cap")) else None),
                    "volume": (int(row.get("volume", 0)) if pd.notna(row.get("volume")) else None),
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
                fund_code=fund_code,
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
            )

        return None

    def discover_funds(self, date: Optional[str] = None, fund_types: Optional[List[str]] = None) -> Dict[str, Set[str]]:
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
            "tefas_crawler": {
                "available": TEFAS_CRAWLER_AVAILABLE,
                "initialized": self.tefas_crawler is not None,
            },
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

    def get_status(self) -> Dict[str, Any]:
        """
        Get status of all data sources

        Returns:
            Dict with status of borsapy and tefas-crawler
        """
        status = {
            "primary_source": self.primary_source,
            "fallback_enabled": self.fallback_enabled,
            "borsapy": {
                "available": BORSAPY_AVAILABLE,
                "initialized": self.borsapy is not None,
                "cache_stats": self.borsapy.get_cache_stats() if self.borsapy else None,
            },
            "tefas_crawler": {
                "available": TEFAS_CRAWLER_AVAILABLE,
                "initialized": self.tefas_crawler is not None,
            },
        }

        # Determine overall health
        if status["borsapy"]["initialized"]:
            status["health"] = "healthy"
        elif status["tefas_crawler"]["initialized"]:
            status["health"] = "degraded"  # Fallback only
        else:
            status["health"] = "unhealthy"

        return status
