"""
Weather Plugin - Hava Durumu Analizi

Version: 1.0.0 (Stable)
Author: FundMind AI
License: MIT

Description:
Open-Meteo API'den hava durumu verilerini toplar ve analiz eder.

Capabilities:
- Real-time weather data collection
- Multi-location support (Istanbul, Ankara, Izmir)
- Temperature, humidity, pressure tracking
- Seasonal pattern detection

Dependencies:
- aiohttp >= 3.9.0
- psycopg2-binary >= 2.9.9

Data Source: Open-Meteo API (Free, no API key required)

Status: ✅ PRODUCTION READY (Version 1.0.0)
"""

from .plugin import WeatherModule

__all__ = ["WeatherModule"]
__version__ = "1.0.0"
