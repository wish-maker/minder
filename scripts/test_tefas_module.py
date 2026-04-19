#!/usr/bin/env python3
"""
TEFAS Module Test Script
Modülün doğru çalışıp çalışmadığını test eder
"""

import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugins.tefas.tefas_module import TefasModule  # noqa: E402


async def test_module():
    """TEFAS modülünü test et"""

    # Test konfigürasyonu
    config = {
        "database": {
            "host": "localhost",
            "port": 5432,
            "database": "fundmind",
            "user": "postgres",
            "password": "id8O+LtRz2OONDKYT9ev+tzOwF/f5lcEcv7eUbIJGI4=",
        },
        "influxdb": {
            "host": "localhost",
            "port": 8086,
            "database": "minder",
            "username": "minder",
            "password": "minder123",
        },
    }

    try:
        # Modül oluştur
        module = TefasModule(config)

        # Kayıt ol
        metadata = await module.register()
        print(f"✅ Modül kaydedildi: {metadata.name} v{metadata.version}")

        # Veri topla
        result = await module.collect_data()
        print(f"✅ Veri toplandı: {result}")

        # Analiz et
        analysis = await module.analyze()
        print(f"✅ Analiz tamamlandı: {analysis}")

        print("\n🎉 Tüm testler başarılı!")
        return True

    except Exception as e:
        print(f"❌ Test başarısız: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_module())
    sys.exit(0 if success else 1)
