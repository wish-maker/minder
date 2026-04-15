#!/usr/bin/env python3
"""
TEFAS Module Test Script
Modülün doğru çalışıp çalışmadığını test eder
"""
import asyncio
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.tefas.tefas_module import TefasModule


async def test_module():
    """TEFAS modülünü test et"""

    # Test konfigürasyonu
    config = {
        'database': {
            'host': 'localhost',
            'port': 5432,
            'database': 'fundmind',
            'user': 'postgres',
            'password': 'id8O+LtRz2OONDKYT9ev+tzOwF/f5lcEcv7eUbIJGI4='
        },
        'influxdb': {
            'host': 'localhost',
            'port': 8086,
            'token': 'minder123',
            'org': 'minder',
            'bucket': 'metrics'
        },
        'qdrant': {
            'host': 'localhost',
            'port': 6333
        },
        'batch_size': 100,
        'historical_start_date': '2020-01-01',
        'collection_interval': 86400
    }

    print("🧪 TEFAS Module Test")
    print("=" * 50)

    try:
        # Modülü oluştur
        print("\n1️⃣ Modül oluşturuluyor...")
        module = TefasModule(config)
        print("✅ Modül oluşturuldu")

        # Modülü kaydet
        print("\n2️⃣ Modül kaydediliyor...")
        metadata = await module.register()
        print(f"✅ Modül kaydedildi: {metadata.name} v{metadata.version}")
        print(f"   Kapasiteler: {', '.join(metadata.capabilities)}")

        # Veri toplama testi (son 7 gün)
        print("\n3️⃣ Veri toplanıyor...")
        since_date = datetime.now() - timedelta(days=7)
        result = await module.collect_data(since=since_date)
        print(f"✅ Veri toplama tamamlandı:")
        print(f"   - Kayıtlar: {result['records_collected']}")
        print(f"   - Güncellenen: {result['records_updated']}")
        print(f"   - Hatalar: {result['errors']}")

        # Analiz testi
        print("\n4️⃣ Analiz yapılıyor...")
        analysis = await module.analyze()
        print(f"✅ Analiz tamamlandı:")
        print(f"   - Metrikler: {len(analysis.get('metrics', {}))} fon")
        print(f"   - Kalıplar: {len(analysis.get('patterns', []))}")
        print(f"   - İçgörüler: {len(analysis.get('insights', []))}")

        # AI eğitim testi
        print("\n5️⃣ AI modeli eğitiliyor...")
        model_result = await module.train_ai(model_type="lstm")
        print(f"✅ Model eğitimi tamamlandı:")
        print(f"   - Model ID: {model_result.get('model_id')}")
        print(f"   - Doğruluk: {model_result.get('accuracy', 0):.2%}")

        # Vektör indeksleme testi
        print("\n6️⃣ Vektör indeksleme yapılıyor...")
        index_result = await module.index_knowledge(force=True)
        print(f"✅ İndeksleme tamamlandı:")
        print(f"   - Vektörler: {index_result['vectors_created']}")
        print(f"   - Koleksiyonlar: {index_result['collections']}")

        # Anomali tespiti testi
        print("\n7️⃣ Anomaliler aranıyor...")
        anomalies = await module.get_anomalies(severity="high", limit=5)
        print(f"✅ Anomali taraması tamamlandı:")
        print(f"   - Bulunan anomali: {len(anomalies)}")

        # Korelasyon testi
        print("\n8️⃣ Korelasyonlar kontrol ediliyor...")
        correlations = await module.get_correlations("interest_rate")
        print(f"✅ Korelasyon analizi tamamlandı:")
        print(f"   - Bulunan korelasyon: {len(correlations)}")

        print("\n" + "=" * 50)
        print("🎉 Tüm testler başarıyla tamamlandı!")

        return True

    except Exception as e:
        print(f"\n❌ Test başarısız oldu: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    from datetime import timedelta

    success = asyncio.run(test_module())
    sys.exit(0 if success else 1)
