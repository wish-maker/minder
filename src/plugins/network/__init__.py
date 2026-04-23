"""
Network Plugin - Ağ Performans İzleme

Version: 1.0.0 (Stable)
Author: FundMind AI
License: MIT

Description:
Sistem ve ağ performans metriklerini toplar, analiz eder ve anormallik tespiti yapar.

Capabilities:
- CPU, Memory, Disk monitoring
- Network traffic analysis
- System performance tracking
- PostgreSQL entegrasyonu

Dependencies:
- psutil >= 5.9.6
- prometheus-client >= 0.20.0
- psycopg2-binary >= 2.9.9

Status: ✅ PRODUCTION READY (Version 1.0.0)
"""

from .plugin import NetworkModule

__all__ = ["NetworkModule"]
__version__ = "1.0.0"
