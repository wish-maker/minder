"""
TEFAS Data Collectors Package

This package contains specialized collectors for different TEFAS data features:
- RiskMetricsCollector: Sharpe ratio, Sortino ratio, max drawdown, volatility
- AllocationCollector: Asset allocation tracking over time
- TaxCollector: Withholding tax rates by fund category
- TechnicalCollector: RSI, MACD, Bollinger Bands, etc.

Each collector is responsible for:
1. Fetching data from UnifiedDataAPI
2. Validating data quality
3. Storing to PostgreSQL
4. Logging collection metrics
5. Error handling and retry logic
"""

from .allocation_collector import AllocationCollector
from .risk_metrics_collector import RiskMetricsCollector
from .tax_collector import TaxCollector

__all__ = [
    "RiskMetricsCollector",
    "AllocationCollector",
    "TaxCollector",
]
