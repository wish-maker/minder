# Minder Modül Geliştirme Rehberi

## 🎯 Yeni Modül Nasıl Oluşturulur?

### 1. Modül Yapısı

```
modules/your-module/
├── __init__.py
├── your_module.py          # Ana modül sınıfı
├── data_sources.py          # API/Veri kaynakları
├── analyzers.py             # Analiz sınıfları
└── README.md                # Modül dokümantasyonu
```

### 2. Zorunlu Metodlar

Her modül `BaseModule`'den türetilmeli ve bu metotları implement etmeli:

```python
from core.module_interface import BaseModule, ModuleMetadata, ModuleStatus
from typing import Dict, Any, Optional
from datetime import datetime

class YourModule(BaseModule):
    async def register(self) -> ModuleMetadata:
        """Modül kimliği ve kapasiteleri"""
        return ModuleMetadata(
            name="your-module",
            version="1.0.0",
            description="Kısa açıklama",
            author="Adınız",
            capabilities=["data_collection", "analysis"],
            data_sources=["api", "database"],
            databases=["postgresql", "influxdb"]
        )
    
    async def collect_data(self, since=None) -> Dict[str, int]:
        """Veri toplama"""
        return {"records_collected": 100}
    
    async def analyze(self) -> Dict[str, Any]:
        """Veri analizi"""
        return {"metrics": {}, "insights": []}
    
    async def train_ai(self, model_type="default") -> Dict[str, Any]:
        """Model eğitimi (opsiyonel)"""
        return {"model_id": "baseline"}
    
    async def index_knowledge(self, force=False) -> Dict[str, int]:
        """RAG vektör indexing (opsiyonel)"""
        return {"vectors_created": 0}
    
    async def get_correlations(self, other_module, type="auto") -> List[Dict]:
        """Çapraz modül korelasyon ipuçları"""
        return []
    
    async def get_anomalies(self, severity="medium", limit=10) -> List[Dict]:
        """Anomali tespiti"""
        return []
```

### 3. Veritabanı Kullanımı

```python
# PostgreSQL (ilişkisel veri)
import psycopg2
from core.module_interface import BaseModule

class YourModule(BaseModule):
    async def collect_data(self):
        conn = psycopg2.connect(
            host=self.config['database']['host'],
            database=self.config['database']['database'],
            user=self.config['database']['user'],
            password=self.config['database']['password']
        )
        # Veri toplama...
        conn.close()

# InfluxDB (time-series)
from influxdb_client import InfluxDBClient

class YourModule(BaseModule):
    async def collect_data(self):
        client = InfluxDBClient(
            url=f"{self.config['influxdb']['host']}:{self.config['influxdb']['port']}",
            token=self.config['influxdb']['token'],
            org=self.config['influxdb']['org']
        )
        # Time-series veri yazma...
```

### 4. Event Bus Kullanımı

```python
from core.event_bus import EventType, Event

class YourModule(BaseModule):
    async def collect_data(self):
        # Veri toplama...
        await self.event_bus.publish(Event(
            type=EventType.DATA_COLLECTED,
            source=self.metadata.name,
            data={"records": 100}
        ))
```

### 5. Modül Kaydı

```yaml
# config.yaml
modules:
  your-module:
    enabled: true
    # Modüle özgü ayarlar
```

Modül `modules/` dizinine koyulduğunda otomatik keşfedilir!

## 📚 Modül Örnekleri

Mevcut modülleri inceleyin:
- `modules/fund/fund_module.py` - Veritabanı entegrasyonu
- `modules/network/network_module.py` - API monitoring
- `modules/crypto/crypto_module.py` - API data fetching

## 🚀 Hızlı Başlangıç

```bash
# Modül dizini oluştur
mkdir -p modules/tefas

# Ana dosyayı oluştur
cat > modules/tefas/tefas_module.py << 'EOF'
from core.module_interface import BaseModule, ModuleMetadata
# ... implementation ...
EOF

# Modül otomatik yüklenir!
```

## ⚠️ Dikkat Edilecekler

1. **Async/Await**: Tüm I/O işlemleri async olmalı
2. **Error Handling**: Hataları yakala, logla, dön
3. **Resource Management**: Bağlantıları düzgün kapat
4. **Testing**: Test yazmayı unutma
5. **Documentation**: README.md ekle
