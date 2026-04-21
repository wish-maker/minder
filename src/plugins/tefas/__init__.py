"""
TEFAS Plugin - Türkiye Yatırım Fonları Analizi

Version: 1.0.0 (Stable)
Author: FundMind AI
License: MIT

Description:
Türkiye'nin önde gelen yatırım fonlarını analiz eden modül.
TEFAS (Türkiye Elektronik Fon Alım Satım Platformu) verilerini toplar,
depolar ve analiz eder.

Capabilities:
- Fon veri toplama (2400+ fon)
- Fiyat performans analizi
- Geriye dönük testler
- PostgreSQL entegrasyonu

Dependencies:
- borsapy >= 0.8.4
- tefas-crawler >= 0.5.0
- psycopg2-binary >= 2.9.9
- pandas >= 2.1.4

Status: ✅ PRODUCTION READY (Version 1.0.0)
"""

from .tefas_module import TefasModule

__all__ = ["TefasModule"]
__version__ = "1.0.0"
