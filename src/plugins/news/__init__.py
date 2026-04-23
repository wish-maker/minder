"""
News Plugin - Haber Toplama ve Analiz

Version: 1.0.0 (Stable)
Author: FundMind AI
License: MIT

Description:
RSS feed'lerinden haber toplama ve analiz etme.

Capabilities:
- RSS feed parsing (BBC, Guardian, NPR)
- News aggregation
- Sentiment analysis
- Trend detection

Dependencies:
- aiohttp >= 3.9.0
- psycopg2-binary >= 2.9.9

Data Sources:
- BBC World News RSS
- Guardian World News RSS
- NPR World News RSS

Status: ✅ PRODUCTION READY (Version 1.0.0)
"""

from .plugin import NewsModule

__all__ = ["NewsModule"]
__version__ = "1.0.0"
