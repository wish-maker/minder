#!/usr/bin/env python3
"""
TEFAS Module Integration Test
Full integration test with database connections
"""
import asyncio
import sys
import os
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plugins.tefas.tefas_module import TefasModule


async def test_full_integration():
    """Tam entegrasyon testi"""

    config = {
        'database': {
            'host': 'postgres',
            'port': 5432,
            'database': 'fundmind',
            'user': 'postgres',
            'password': 'id8O+LtRz2OONDKYT9ev+tzOwF/f5lcEcv7eUbIJGI4='
        },
        'influxdb': {
            'host': 'influxdb',
            'port': 8086,
            'token': 'minder123',
            'org': 'minder',
            'bucket': 'metrics'
        },
        'qdrant': {
            'host': 'qdrant',
            'port': 6333
        },
        'batch_size': 100,
        'historical_start_date': '2020-01-01',
        'collection_interval': 86400
    }

    print("🧪 TEFAS Module Integration Test")
    print("=" * 60)

    try:
        # 1. Modülü oluştur
        print("\n1️⃣  Modül başlatılıyor...")
        module = TefasModule(config)
        print("   ✅ Modül oluşturuldu")

        # 2. Metadata kontrolü
        print("\n2️⃣  Modül metadata alınıyor...")
        metadata = await module.register()
        print(f"   ✅ Modül: {metadata.name} v{metadata.version}")
        print(f"   📝 Açıklama: {metadata.description}")
        print(f"   🔧 Kapasiteler: {', '.join(metadata.capabilities[:5])}...")

        # 3. Veri toplama (son 3 gün - hızlı test)
        print("\n3️⃣  Veri toplanıyor (son 3 gün)...")
        since_date = datetime.now() - timedelta(days=3)
        result = await module.collect_data(since=since_date)
        print(f"   ✅ Toplanan kayıt: {result['records_collected']}")
        print(f"   ✅ Güncellenen: {result['records_updated']}")
        print(f"   ⚠️  Hatalar: {result['errors']}")

        if result['errors'] > 0:
            print("   ⚠️  Bazı hatalar oluştu ama devam ediliyor")

        # 4. Analiz
        print("\n4️⃣  Analiz yapılıyor...")
        analysis = await module.analyze()
        metrics_count = len(analysis.get('metrics', {}))
        insights_count = len(analysis.get('insights', []))
        print(f"   ✅ Analiz edilen fon: {metrics_count}")
        print(f"   ✅ İçgörü sayısı: {insights_count}")

        if metrics_count > 0:
            print("\n   📊 Örnek metrikler:")
            for fund_code, metrics in list(analysis['metrics'].items())[:3]:
                print(f"      {fund_code}:")
                print(f"         - Günlük getiri: {metrics['avg_daily_return']:.4f}")
                print(f"         - Volatilite: {metrics['volatility']:.4f}")
                print(f"         - Sharpe oranı: {metrics['sharpe_ratio']:.2f}")

        # 5. AI eğitimi (basic test)
        print("\n5️⃣  AI modeli eğitimi...")
        model_result = await module.train_ai(model_type="lstm")
        print(f"   ✅ Model ID: {model_result.get('model_id')}")
        if 'error' not in model_result:
            print(f"   ✅ Doğruluk: {model_result.get('accuracy', 0):.1%}")

        # 6. Vektör indeksleme
        print("\n6️⃣  Vektör indeksleme...")
        index_result = await module.index_knowledge(force=False)
        print(f"   ✅ Vektörler: {index_result['vectors_created']}")
        print(f"   ✅ Koleksiyonlar: {index_result['collections']}")

        # 7. Anomali tespiti
        print("\n7️⃣  Anomali tespiti...")
        anomalies = await module.get_anomalies(severity="high", limit=5)
        print(f"   ✅ Bulunan anomali: {len(anomalies)}")

        # 8. Korelasyon analizi
        print("\n8️⃣  Korelasyon analizi...")
        correlations = await module.get_correlations("interest_rate")
        print(f"   ✅ Korelasyon sayısı: {len(correlations)}")

        print("\n" + "=" * 60)
        print("🎉 Entegrasyon testi başarıyla tamamlandı!")

        return True

    except Exception as e:
        print(f"\n❌ Test başarısız: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_full_integration())
    sys.exit(0 if success else 1)
