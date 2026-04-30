"""
Crypto Plugin - Kripto Para Analizi

Version: 1.0.0 (Stable)
Author: Minder
License: MIT

Description:
Çoklu kaynaklı kripto para fiyat takibi ve analizi.

Capabilities:
- Multi-source price tracking (Binance, CoinGecko, Kraken)
- Automatic fallback mechanism
- Price history and analytics
- Market cap and volume tracking

Dependencies:
- aiohttp >= 3.9.0
- psycopg2-binary >= 2.9.9
- pyyaml >= 6.0.1

Data Sources:
- Binance API (primary)
- CoinGecko API (fallback)
- Kraken API (fallback)

Status: ✅ PRODUCTION READY (Version 1.0.0)
"""

from .plugin import CryptoModule

__all__ = ["CryptoModule"]
__version__ = "1.0.0"
