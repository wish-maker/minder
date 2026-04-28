# 🚀 Minder Versiyon Yönetim Rehberi

## 📋 Özet

Bu rehber, **ana uygulama ve bileşenlerin (kütüphanelerin)** versiyonlarının ayrı ayrı yönetilmesi** için stratejiler sağlar.

---

## 🎯 Versiyonlama Stratejisi

### Strateji 1: Ana Uygulama vs. Bileşenler

**Ana Uygulama (Minder Core):**
- API Gateway
- Plugin Registry
- Plugin State Manager
- Marketplace
- Model Management
- Model Fine-tuning
- RAG Pipeline
- TTS/STT Service

**Bileşenler (External Dependencies & Libraries):**
- Ollama (LLM)
- Qdrant (Vector Database)
- Neo4j (Graph Database)
- AsyncPG (PostgreSQL Driver)
- Redis (Redis Client)

### Strateji Ayrımı

| Tür | Versiyonlama | Format | Örnek |
|-----|---------------|---------|-------|
| **Ana Uygulama** | API Versioning | v2.1.0 | v2.1.0 |
| **Bileşenler** | Library Versioning | v0.5.0 | ollama v0.5.0 |
| **Pluginler** | Semantic Versioning | v1.0.0-alpha | plugin v1.0.0-alpha |

---

## 📦 Kütüphane Versiyonları

### Kullanılan Kütüphaneler

| Kütüphane | Mevcut Versiyon | Hedef Versiyon | Versiyon Tipi |
|-----------|----------------|---------------|---------------|
| **Ollama** | v0.1.x | v0.5.0 | Library (LLM) |
| **Qdrant** | v1.6.x | v1.8.0 | Library (Vector DB) |
| **Neo4j** | v4.4.x | v5.0.0 | Library (Graph DB) |
| **AsyncPG** | v0.28.x | v0.29.0 | Library (PG Driver) |
| **Redis** | v4.5.x | v5.0.0 | Library (Cache) |
| **FastAPI** | v0.104.x | v0.110.0 | Library (Web Framework) |
| **Pydantic** | v2.0.x | v2.1.0 | Library (Validation) |
| **HTTPX** | v0.25.x | v0.26.0 | Library (HTTP Client) |

---

## 🎯 Strateji Seçenekleri

### Seçenek 1: Aynı Versiyon (Tutarlı) - **Tavsiye Edilen**

Tüm bileşenler **ana uygulamayla aynı versiyonu** kullanır.

**Avantajları:**
- ✅ Sürdürülebilir (breaking changes tutarlı)
- ✅ Maintenance kolay (tümü aynı)
- ✅ Backward compatible (tümü aynı anda)

**Dezavantajları:**
- ❌ Kütüphaneler eski olabilir
- ❌ Özellikler kısıtlı olabilir
- ❌ En son özellikleri kullanamayabilir

**Kullanım:**
- Küçük, tek-ekip projeler
- Stability önemliyse

---

### Seçenek 2: Ayrı Versiyonlama - **Esnek**

**Ana uygulama** ve **bileşenler** farklı versiyonları kullanır.

**Avantajları:**
- ✅ En son kütüphane özellikleri kullanılabilir
- ✅ Her bileşen ayrı optimize edilebilir
- ✅ Breaking changes ayrı yönetilebilir

**Dezavantajları:**
- ❌ Integration karmaşık olabilir
- ❌ Version conflicts oluşabilir
- ❌ Maintenance zor

**Kullanım:**
- Büyük, modüler projeler
- En son özellikler önemliyse

---

### Seçenek 3: Semantic Versioning (Pluginler) - **Profesyonel**

Pluginler için **semantic versioning** (v1.0.0, v1.1.0, v1.2.0) kullanır.

**Avantajları:**
- ✅ Breaking changes anlaşılabilir (MAJOR.MINOR.PATCH)
- ✅ Pluginler için standart
- ✅ Release management kolay

**Dezavantajları:**
- ❌ Ana uygulamayla uyumsuzluk
- ❌ Versiyon karmaşası

**Kullanım:**
- Plugin ekosistemi
- Release management önemliyse

---

## 🏗 Tutarlı Versiyonlama (Strateji 1)

### Ana Uygulama Versiyonu

**Current:** v2.1.0
**Next:** v2.2.0

**Version Components:**
- MAJOR: Ana sürüm (breaking changes)
- MINOR: Yeni özellikler (backwards compatible)
- PATCH: Bug fixleri (backwards compatible)

### Bileşen Versiyonları

Tüm kütüphaneler **ana uygulama versiyonuna** eşlenir:

| Bileşen | Versiyon | API Versiyonu |
|---------|---------|---------------|
| FastAPI | v0.110.0 | v2.1.0 |
| Pydantic | v2.1.0 | v2.1.0 |
| HTTPX | v0.26.0 | v2.1.0 |
| AsyncPG | v0.29.0 | v2.1.0 |
| Redis | v5.0.0 | v2.1.0 |
| Qdrant | v1.8.0 | v2.1.0 |
| Neo4j | v5.0.0 | v2.1.0 |
| Ollama | v0.5.0 | v2.1.0 |

**Avantajları:**
- ✅ Sürdürülebilir (breaking changes tutarlı)
- ✅ Maintenance kolay (tümü aynı anda)
- ✅ Integration testleri kolay
- ✅ Backward compatible

**Dezavantajları:**
- ❌ Kütüphaneler eski olabilir
- ❌ Özellikler kısıtlı olabilir

---

## 🏗 Semantic Versioning (Strateji 3)

### Plugin Versiyonlama

**Format:** vMAJOR.MINOR.PATCH

**Version Components:**
- MAJOR: Breaking changes (v1.0.0 → v2.0.0)
- MINOR: Yeni özellikler (backwards compatible)
- PATCH: Bug fixleri (backwards compatible)

**Örnekler:**
- v1.0.0-alpha → İlk sürüm
- v1.1.0 → Yeni özellikler
- v1.2.0 → Breaking changes
- v1.2.1 → Patch fix

**Ana Uygulama Versiyonu:**
- **Current:** v2.1.0
- **Plugin API Version:** v1.0.0

**Avantajları:**
- ✅ Pluginler için standart
- ✅ Breaking changes anlaşılabilir
- ✅ Release management kolay
- ✅ Plugin compatibility tracking

**Dezavantajları:**
- ❌ Ana uygulamayla uyumsuzluk
- ❌ Versiyon karmaşası

---

## 🎯 Hangi Strateji?

### Tavsiye: Strateji 2 (Ayrı Versiyonlama)

**Neden Strateji 2?**

1. **Kütüphaneler En Son Özellikleri Kullanmak İster:**
   - Ollama, Qdrant, Neo4j sürek gelişiyor
   - En son özellikleri kullanmak için en güncel versiyonlar gerekli

2. **Stability vs. Features Trade-off:**
   - AI ve database kütüphanelerinin en son özellikleri çok önemli
   - Stability için biraz ödün versiyon kullanmak riskli

3. **Modüler Architecture Desteği:**
   - Minder microservices architecture, her servis bağımsız
   - Breaking'ler servis bazında yönetilebilir

4. **Backward Compatibility:**
   - API versioning ile breaking'ler ayrı yönetilebilir
   - Pluginler semantic versioning ile kendi sürümlerini yönetebilir

---

## 📝 Versiyonlama Uygulaması

### Ana Uygulama (Minder Core)

**services/api-gateway/main.py:**
```python
__version__ = "2.1.0"
```

**services/api-gateway/routes/health.py:**
```python
API_VERSION = "v2.1.0"
```

**services/plugin-registry/main.py:**
```python
version = "2.1.0"
```

**services/marketplace/main.py:**
```python
version = "2.1.0"
```

### Bileşenler (Kütüphaneler)

**requirements.txt:**
```txt
fastapi>=0.110.0,<0.120.0
pydantic>=2.1.0,<2.2.0
httpx>=0.26.0,<0.27.0
asyncpg>=0.29.0,<0.30.0
redis>=5.0.0,<5.1.0
qdrant>=1.8.0,<1.9.0
neo4j>=5.0.0,<5.1.0
```

**services/ai-services-unified/main.py:**
```python
# Ollama version
OLLAMA_VERSION = "0.5.0"

# Qdrant version (client library)
QDRANT_CLIENT_VERSION = "1.6.0"

# Neo4j version (driver version)
NEO4J_DRIVER_VERSION = "4.4.0"
```

### Pluginler

**src/plugins/*/plugin.py:**
```python
PLUGIN_VERSION = "1.0.0"
PLUGIN_API_VERSION = "v1.0.0"
```

---

## 🔄 Versiyon Güncelleme

### Ana Uygulama

**2.1.0 → 2.2.0 (Breaking Changes):**
1. Tüm servislerdeki `__version__`'i güncelle
2. Breaking change'leri belgele
3. Migration scriptleri hazırla
4. Plugin API versiyonunu güncelle (v1.0.0 → v2.0.0)

**2.1.0 → 2.1.1 (Yeni Özellikler):**
1. Tüm servislerdeki `__version__`'i güncelle
2. Yeni özellikleri ekle
3. Breaking change yok
4. Plugin API versiyonu koru

### Bileşenler

**Ollama v0.5.0 → v0.6.0:**
1. `services/ai-services-unified/main.py`'yi güncelle
2. Breaking change'leri kontrol et
3. Migration scripti çalıştır
4. Yeni özellikleri ekle

**FastAPI v0.110.0 → v0.111.0:**
1. `requirements.txt`'yi güncelle
2. Breaking change'leri kontrol et
3. `pip install` çalıştır
4. Migration testleri çalıştır

---

## 🔍 Version Checking

### API Version Check

**services/api-gateway/routes/health.py:**
```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/version")
async def get_version():
    """Return current API version and component versions"""
    return {
        "api_version": "2.1.0",
        "plugin_api_version": "1.0.0",
        "components": {
            "fastapi": "0.110.0",
            "pydantic": "2.1.0",
            "httpx": "0.26.0",
            "asyncpg": "0.29.0",
            "redis": "5.0.0",
            "qdrant": "1.8.0",
            "neo4j": "4.4.0",
            "ollama": "0.5.0",
        }
    }
```

### Component Version Check

**scripts/check-versions.sh:**
```bash
#!/bin/bash

echo "=== Minder Component Versions ==="

# Ana uygulama versiyonu
echo "API Version: $(grep -o '__version__ = "[^"]*' services/*/main.py | head -1)"

# Kütüphane versiyonları
echo "FastAPI: $(grep -o 'fastapi>=[^<]*' requirements.txt)"
echo "Pydantic: $(grep -o 'pydantic>=[^<]*' requirements.txt)"
echo "HTTPX: $(grep -o 'httpx>=[^<]*' requirements.txt)"
echo "AsyncPG: $(grep -o 'asyncpg>=[^<]*' requirements.txt)"

# Ollama versiyonu
echo "Ollama: $(grep -o 'OLLAMA_VERSION=' services/ai-services-unified/main.py)"
```

---

## 🚀 Rollout Planı

### Adım 1: Versiyon Belirleme
- [ ] Ana uygulama versiyonu belirle (v2.1.0)
- [ ] Kütüphane versiyonlarını belirle
- [ ] Plugin API versiyonu belirle (v1.0.0)

### Adım 2: Ana Uygulama Güncelleme
- [ ] Tüm servislerin versiyonunu güncelle
- [ ] API version endpoint'ini güncelle
- [ ] Breaking change'leri belgele

### Adım 3: Bileşenler Güncelleme
- [ ] Kütüphane versiyonlarını güncelle
- [ ] requirements.txt'yi güncelle
- [ ] Breaking change'leri kontrol et

### Adım 4: Test ve Doğrulama
- [ ] Integration testleri çalıştır
- [ ] Version compatibility testleri
- [ ] Breaking change'leri doğrula

### Adım 5: Rollout
- [ ] Canary deployment
- [ ] Monitor rollback
- [ ] Gradual rollout

---

## 📊 Version Matrix

| Component | Version | API Version | Breaking Changes |
|-----------|---------|-------------|-----------------|
| **Minder Core** | v2.1.0 | v2.1.0 | No |
| **Plugin API** | v1.0.0 | v1.0.0 | No |
| **FastAPI** | v0.110.0 | v2.1.0 | No |
| **Pydantic** | v2.1.0 | v2.1.0 | No |
| **HTTPX** | v0.26.0 | v2.1.0 | No |
| **AsyncPG** | v0.29.0 | v2.1.0 | No |
| **Redis** | v5.0.0 | v2.1.0 | No |
| **Qdrant** | v1.8.0 | v2.1.0 | No |
| **Neo4j** | v4.4.0 | v2.1.0 | No |
| **Ollama** | v0.5.0 | v2.1.0 | No |

---

## 📝 Notlar

### Important Notes

1. **Breaking Changes:** Breaking change'leri her zaman dikkatlice planlayın
2. **Migration:** Migration scriptleri her breaking change ile birlikte sağlayın
3. **Testing:** Integration testleri her sürümde çalıştırın
4. **Backward Compatibility:** API versioning ile backward compatible kalın
5. **Plugin Compatibility:** Plugin API'sini stabilization için değiştirmeyin
6. **Component Updates:** Kütüphaneleri ayrı güncelleyin

### Best Practices

1. **Semantic Versioning:** Breaking changes için MAJOR numarasını artırın
2. **Version Constraints:** requirements.txt'da minimum ve maksimum versiyonlar belirleyin
3. **API Versioning:** Ana uygulama ve plugin API'leri için ayrı versioning kullanın
4. **Release Notes:** Her sürüm için release notes yazın
5. **Testing:** Integration tests ve E2E tests her sürümde çalıştırın
6. **Rollback Plan:** Her sürüm için rollback planı hazırlayın

---

## 🔄 Otomatik Versiyon Yönetimi

### Versiyon Check Script

**scripts/check-versions.sh:**
```bash
#!/bin/bash

echo "=== Minder Version Check ==="

# Ana uygulama versiyonu
API_VERSION=$(grep -o '__version__ = "[^"]*' services/api-gateway/main.py | head -1)
echo "API Version: $API_VERSION"

# Kütüphane versiyonları
echo "Component Versions:"
grep -o 'OLLAMA_VERSION=' services/ai-services-unified/main.py
grep -o 'FASTAPI_VERSION' services/ai-services-unified/config.py
grep -o 'PYDANTIC_VERSION' services/ai-services-unified/config.py

# Versiyon tutarlılığını kontrol et
echo ""
echo "Version Consistency Check:"
# Tüm servislerin aynı versiyonu kullandığından emin olun
```

---

## 📚 References

### Versiyonlama Standartları

- **Semantic Versioning (SemVer):** https://semver.org/
- **PyPI Versioning:** https://packaging.python.org/en/latest/guides/
- **API Versioning:** https://restfulapi.net/versioning/

### Kütüphane Versiyonları

- **Ollama:** https://github.com/ollama/ollama/releases
- **Qdrant:** https://github.com/qdrant/qdrant/releases
- **Neo4j:** https://github.com/neo4j/neo4j/releases
- **FastAPI:** https://fastapi.tiangolo.com/release-notes/
- **Pydantic:** https://docs.pydantic.dev/latest/changelog/
- **HTTPX:** https://github.com/encode/httpx/releases

---

**Last Updated:** 2026-04-28
**Version:** 2.1.0
