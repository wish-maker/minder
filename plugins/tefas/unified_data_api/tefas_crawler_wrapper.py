"""
TefasCrawlerWrapper - tefas-crawler wrapper for fallback support

Provides basic fund data collection using tefas-crawler package
"""

import logging
from typing import Dict, List, Optional, Set

import pandas as pd

try:
    from tefas import Crawler

    TEFAS_CRAWLER_AVAILABLE = True
except ImportError:
    TEFAS_CRAWLER_AVAILABLE = False
    logging.warning("tefas-crawler not installed. Install with: pip install tefas-crawler")

logger = logging.getLogger("minder.tefas.tefas_crawler_wrapper")


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

    def discover_funds(self, date: str, fund_types: Optional[List[str]] = None) -> Dict[str, Set[str]]:
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
