"""
Unified Data API - TEFAS data source abstraction layer
Supports borsapy and tefas-crawler with automatic fallback mechanism

This module provides a unified interface for accessing TEFAS data from multiple sources
with automatic fallback, caching, and error handling.
"""

from .borsapy_wrapper import BORSAPY_AVAILABLE, BorsapyWrapper
from .tefas_crawler_wrapper import TEFAS_CRAWLER_AVAILABLE, TefasCrawlerWrapper
from .unified_api import UnifiedDataAPI

__all__ = [
    "UnifiedDataAPI",
    "BorsapyWrapper",
    "TefasCrawlerWrapper",
    "BORSAPY_AVAILABLE",
    "TEFAS_CRAWLER_AVAILABLE",
]
