# 🚀 Minder Versiyon Yönetim Rehberi

## 📋 Özet

Bu rehber, **ana uygulamanın ve bileşenlerin (kütüphanelerin) versiyonlarının ayrı ayrı yönetilmesi** için stratejiler sağlar.

---

## 🎯 Versiyon Yönetim Stratejisi

### Strateji 2: Ayrı Versiyonlama (Esnek) 🎯

**Ana Uygulama** ve **Bileşenler (Kütüphaneler)** **farklı versiyonlama** stratejileri kullanır:

- **Ana Uygulama (Minder Core):** API Versioning (vMAJOR.MINOR.PATCH)
- **Bileşenler:** Library Versioning (MAJOR.MINOR.PATCH)

**Avantajları:**
- ✅ En güncel kütüphane özellikleri kullanılabilir
- ✅ Breaking changes ayrı yönetilebilir
- ✅ Her bileşen için optimize edilebilir sürüm döngüsü
- ✅ Plug-in uyumluluğu korur

**Dezavantajları:**
- ❌ Versiyon karmaşası artabilir
- ❌ Integration testleri zor olabilir
- ❌ Maintenance karmaşık olabilir

---

## 📊 Mevcut Versiyonlar

### Ana Uygulama (Minder Core)

| Servis | Dosya | Versiyon | Strateji |
|--------|-------|----------|----------|
| **API Gateway** | main.py | v2.1.0 | API Versioning |
| **Plugin Registry** | main.py | v2.1.0 | API Versioning |
| **Plugin State Manager** | settings.py | v2.1.0 | API Versioning |
| **Marketplace** | main.py | v2.1.0 | API Versioning |
| **Model Management** | main.py | v2.1.0 | API Versioning |
| **Model Fine-tuning** | main.py | v2.1.0 | API Versioning |
| **TTS/STT Service** | main.py | v2.1.0 | API Versioning |

**Tutarlılık:** %100 (tümü v2.1.0)

### Bileşenler (Kütüphaneler)

| Bileşen | Mevcut | Hedef | Strateji |
|---------|--------|-------|----------|
| **FastAPI** | v0.110.0 | v0.120.0 | Library Versioning |
| **Pydantic** | v2.1.0 | v2.2.0 | Library Versioning |
| **HTTPX** | v0.26.0 | v0.28.0 | Library Versioning |
| **AsyncPG** | v0.29.0 | v0.30.0 | Library Versioning |
| **Redis (Client)** | v5.0.0 | v5.1.0 | Library Versioning |
| **Qdrant** | v1.8.0 | v1.10.0 | Library Versioning |
| **Neo4j** | v4.4.0 | v5.0.0 | Library Versioning |
| **Ollama** | v0.5.7 | v0.5.8 | Library Versioning |

---

## 🎯 Versiyon Yönetim

### Ana Uygulama Versiyonları

**Tutarlılık ilkesi:** Tüm ana uygulama servisleri aynı versiyonu kullanır (v2.1.0)

**API Versioning Format:** vMAJOR.MINOR.PATCH

| Component | MAJOR | MINOR | PATCH | Format |
|-----------|-------|-------|-------|--------|
| **Minder Core** | 2 | 1 | 0 | v2.1.0 |

**Breaking Changes:** Core API versiyonu v2.1.0'a yükseltildiğinde API breaking changes olabilir.

### Bileşen Versiyonları

Her bileşenin kendi sürüm döngüsü vardır:

**FastAPI:**
- Current: v0.110.0
- Next: v0.120.0
- Breaking Changes: 1.1.0 → 1.2.0'da olabilir

**Pydantic:**
- Current: v2.1.0
- Next: v2.2.0
- Breaking Changes: 2.0 → 2.1.0'da olabilir

**HTTPX:**
- Current: v0.26.0
- Next: v0.28.0
- Breaking Changes: 0.25 → 0.26'da olabilir

**AsyncPG:**
- Current: v0.29.0
- Next: v0.30.0
- Breaking Changes: 0.28 → 0.29'da olabilir

**Redis:**
- Current: v5.0.0
- Next: v5.1.0
- Breaking Changes: 4.x → 5.x'de olabilir

**Qdrant:**
- Current: v1.8.0
- Next: v1.10.0
- Breaking Changes: 1.7 → 1.8'da olabilir

**Neo4j:**
- Current: v4.4.0
- Next: v5.0.0
- Breaking Changes: 4.x → 5.x'de olabilir (büyük jump)

**Ollama:**
- Current: v0.5.7
- Next: v0.5.8
- Breaking Changes: Minimal (her sürümde küçük değişiklikler)

---

## 🔄 Versiyon Güncelleme Yöntemleri

### Ana Uygulama Versiyonunu Güncelleme

**Tüm servisleri aynı anda güncelle:**

```bash
cd /root/minder

# Ana servislerdeki versiyonları güncelle
find services/ -type f \( -name "main.py" -o -name "config.py" -o -name "settings.py" \) | \
  xargs sed -i 's/__version__ = "v2\.1\.0"/__version__ = "v2\.2\.0"/g; s/API_VERSION = "v2\.1\.0"/API_VERSION = "v2\.2\.0"/g; s/version = "v2\.1\.0"/version = "v2\.2\.0"/g'

# Doğrulama
grep -r "version.*v2\.2\.0\|api_version.*v2\.2\.0" services/ | wc -l

echo "✅ Ana uygulama v2.2.0'a güncellendi"

# Servisleri yeniden başlat
docker-compose restart

# Bekletme (15 saniye)
sleep 15

# Durum kontrolü
docker-compose ps
```

### Bileşen Versiyonunu Güncelleme

**FastAPI'yi güncelle:**

```bash
cd /root/minder

# requirements.txt'de FastAPI versiyonunu güncelle
sed -i 's/fastapi>=0\.110\.0,<0\.120\.0/fastapi>=0.120.0,<0.130\.0/g' requirements.txt

# Yükle
pip install --upgrade fastapi

# Doğrulama
pip show fastapi
```

**Pydantic'yi güncelle:**

```bash
cd /root/minder

# requirements.txt'de Pydantic versiyonunu güncelle
sed -i 's/pydantic>=2\.1\.0,<2\.2\.0/pydantic>=2.2\.0,<2\.3\.0/g' requirements.txt

# Yükle
pip install --upgrade pydantic

# Doğrulama
pip show pydantic
```

**Diğer Bileşenleri Güncelleme:**

```bash
cd /root/minder

# requirements.txt'de diğer bileşenleri güncelle
sed -i 's/httpx>=0\.26\.0,<0\.28\.0/httpx>=0.28.0,<0\.29\.0/g' requirements.txt
sed -i 's/asyncpg>=0\.29\.0,<0\.30\.0/asyncpg>=0.30\.0,<0\.31\.0/g' requirements.txt

# Yükle
pip install --upgrade httpx asyncpg

# Doğrulama
pip show httpx asyncpg
```

---

## 🔍 Doğrulama Komutları

### Ana Uygulama

```bash
# Tüm servislerin versiyonunu kontrol et
grep -r "version.*v2\.2\.0\|api_version.*v2\.2\.0" services/ | wc -l

# Belirli servislerin versiyonunu kontrol et
grep -r "version.*v2\.2\.0\|api_version.*v2\.2\.0" services/api-gateway/main.py
```

### Bileşenler

```bash
# requirements.txt'deki versiyonları kontrol et
cat requirements.txt | grep -E "fastapi|pydantic|httpx|asyncpg"

# Yüklü versiyonları kontrol et
pip list | grep -E "fastapi|pydantic|httpx|asyncpg"
```

### API Version Endpoint

```bash
# API versiyonunu sorgula
curl http://localhost:8000/v1/version | jq
```

Beklenen çıktı:
```json
{
  "api_version": "v2.1.0",
  "component_versions": {
    "fastapi": "0.110.0",
    "pydantic": "2.1.0",
    "httpx": "0.26.0",
    "asyncpg": "0.29.0",
    "redis": "5.0.0",
    "qdrant": "1.8.0",
    "neo4j": "4.4.0",
    "ollama": "0.5.7"
  }
}
```

---

## 📊 Version Matrix

| Component | Type | Current | Next | Breaking Change |
|-----------|------|---------|------|-----------------|
| **Minder Core** | API | v2.1.0 | v2.2.0 | API breaking |
| **FastAPI** | Library | v0.110.0 | v0.120.0 | v1.1.0 |
| **Pydantic** | Library | v2.1.0 | v2.2.0 | v2.0.0 |
| **HTTPX** | Library | v0.26.0 | v0.28.0 | v0.25.0 |
| **AsyncPG** | Library | v0.29.0 | v0.30.0 | v0.28.0 |
| **Redis** | Library | v5.0.0 | v5.1.0 | v4.x |
| **Qdrant** | Library | v1.8.0 | v1.10.0 | v1.7.0 |
| **Neo4j** | Library | v4.4.0 | v5.0.0 | v4.x (large) |
| **Ollama** | Library | v0.5.7 | v0.5.8 | v0.5.0 (small) |

---

## 🚀 Güncelleme Stratejisi

### Adım 1: Bileşenleri Güncelle

```bash
# 1. requirements.txt'yi güncelle
cd /root/minder

# FastAPI, Pydantic, HTTPX, AsyncPG
sed -i 's/fastapi>=0\.110\.0,<0\.120\.0/fastapi>=0.120.0,<0\.130\.0/g' requirements.txt
sed -i 's/pydantic>=2\.1\.0,<2\.2\.0/pydantic>=2.2\.0,<2\.3\.0/g' requirements.txt
sed -i 's/httpx>=0\.26\.0,<0\.28\.0/httpx>=0.28.0,<0\.29\.0/g' requirements.txt
sed -i 's/asyncpg>=0\.29\.0,<0\.30\.0/asyncpg>=0.30\.0,<0\.31\.0/g' requirements.txt

# 2. Yükle
pip install --upgrade fastapi pydantic httpx asyncpg

# 3. Doğrulama
pip show fastapi pydantic httpx asyncpg

# 4. Servisleri yeniden başlat
docker-compose restart

# 5. Bekletme (15 saniye)
sleep 15

# 6. Durum kontrolü
docker-compose ps
```

### Adım 2: Ana Uygulamayı Güncelle

```bash
cd /root/minder

# Ana servislerdeki versiyonları güncelle
find services/ -type f \( -name "main.py" -o -name "config.py" -o -name "settings.py" \) | \
  xargs sed -i 's/__version__ = "v2\.1\.0"/__version__ = "v2\.2\.0"/g; s/API_VERSION = "v2\.1\.0"/API_VERSION = "v2\.2\.0"/g; s/version = "v2\.1\.0"/version = "v2\.2\.0"/g'

# Doğrulama
grep -r "version.*v2\.2\.0\|api_version.*v2\.2\.0" services/ | wc -l

echo "✅ Ana uygulama v2.2.0'a güncellendi"

# Servisleri yeniden başlat
docker-compose restart

# Bekletme (15 saniye)
sleep 15

# Durum kontrolü
docker-compose ps
```

---

## 🔍 Sorun Giderme

### Versiyon Uyuşmazlıkları

```bash
# Servis versiyonlarını kontrol et
curl http://localhost:8000/v1/health

# API versiyonunu kontrol et
curl http://localhost:8000/v1/version

# Bileşen versiyonlarını kontrol et
python3 -c "import fastapi, pydantic; print(f'FastAPI: {fastapi.__version__}, Pydantic: {pydantic.VERSION}')"
```

### Breaking Change Sorunları

**Eğer breaking change varsa:**

1. Migration scriptlerini çalıştır
2. API documentation'ı güncelle
3. Breaking changes'i belgele
4. Canary deployment yap
5. Rollback planı hazırla

---

## 📝 Breaking Change'ler

### v2.2.0 Breaking Change'leri

**Eğer v2.2.0'da breaking change varsa:**

1. **API Gateway Breaking Changes:**
   - Plugin API endpoints değiştiyse
   - Authentication flow değiştiyse
   - Response format değiştiyse

2. **Pydantic v2.2.0 Breaking Changes:**
   - Validation behavior değiştiyse
   - Model serialization değiştiyse
   - Type hint requirements değiştiyse

3. **FastAPI v0.120.0 Breaking Changes:**
   - Request/response handling değiştiyse
   - Middleware hooks değiştiyse
   - Dependency injection değiştiyse

**Migration Checklist:**
- [ ] API documentation güncellendi
- [ ] Breaking changes belgelendi
- [ ] Migration scriptleri çalıştırıldı
- [ ] Integration testleri çalıştırıldı
- [ ] E2E testleri çalıştırıldı
- [ ] Canary deployment yapıldı
- [ ] Rollback planı hazırlandı

---

## 🔄 Rollout Planı

### Canary Deployment

```bash
# 1. Canary deployment (küçük subset)
./deploy.sh canary --subset=10%

# 2. Monitor (10 dakika)
./deploy.sh monitor --duration=600

# 3. Gradual rollout
./deploy.sh rollout --percentage=20
./deploy.sh monitor --duration=300

# 4. Full rollout
./deploy.sh rollout --percentage=100

# 5. Monitor
./deploy.sh monitor --duration=1800
```

### Gradual Rollout

```bash
# 1. Staging'e deploy et
./deploy.sh deploy --environment=staging

# 2. Testleri çalıştır
pytest tests/integration/ tests/e2e/

# 3. Production'a deploy et
./deploy.sh deploy --environment=production

# 4. Monitor
./deploy.sh monitor --duration=1800
```

---

## 📝 Notlar

### Önemli Notlar

1. **Version Ayrımı:** Ana uygulama ve bileşenler farklı sürümleri kullanır
2. **Tutarlılık:** Tüm ana uygulama servisleri aynı versiyonu kullanır
3. **Breaking Changes:** Breaking change'ler çok dikkatlice planlanmalı
4. **Testing:** Her güncellemeden önce integration ve E2E testleri çalıştırılmalı
5. **Migration:** Breaking change'ler için migration scriptleri sağlanmalı
6. **Documentation:** Her sürüm için changelog ve migration guide sağlanmalı

### Best Practices

1. **Semantic Versioning:** Breaking changes için MAJOR numarasını artırın
2. **Library Updates:** En son kütüphane özellikleri kullanın
3. **Backward Compatibility:** Mümkünse backward compatible kalın
4. **Migration Scripts:** Breaking change'ler için migration scriptleri sağlayın
5. **Integration Testing:** Her güncellemeden önce integration testleri çalıştırın
6. **Canary Deployment:** Production'a rollout öncesi canary deployment kullanın
7. **Monitoring:** Rollout sırasında monitoring yapın
8. **Rollback Plan:** Her sürüm için rollback planı hazırlayın

---

## 🚀 Hızlı Başlatma

**Strateji 2'yi uygulamak için hızlı başlatma komutları:**

```bash
cd /root/minder

# 1. requirements.txt'yi güncelle
sed -i 's/fastapi>=0\.110\.0,<0\.120\.0/fastapi>=0.120\.0,<0\.130\.0/g; s/pydantic>=2\.1\.0,<2\.2\.0/pydantic>=2\.2\.0,<2\.3\.0/g' requirements.txt

# 2. Bileşenleri güncelle
pip install --upgrade fastapi pydantic httpx asyncpg

# 3. Ana uygulamayı güncelle (v2.2.0)
find services/ -type f \( -name "main.py" -o -name "config.py" -o -name "settings.py" \) | \
  xargs sed -i 's/__version__ = "v2\.1\.0"/__version__ = "v2\.2\.0"/g; s/API_VERSION = "v2\.1\.0"/API_VERSION = "v2\.2\.0"/g; s/version = "v2\.1\.0"/version = "v2\.2\.0"/g'

# 4. Servisleri yeniden başlat
docker-compose restart

# 5. Bekletme (15 saniye)
sleep 15

# 6. Durum kontrolü
docker-compose ps
```

---

## 📞 Rollback Planı

**Eğer v2.2.0 sorun yaratırsa:**

```bash
# Git'e geri dön
cd /root/minder
git checkout HEAD~1 -- .

# Servisleri yeniden başlat
docker-compose restart

# Bekletme
sleep 10

# Durum kontrolü
docker-compose ps
```

---

## 📊 Sonuç Matrisi

| Component | Version | Strategy | Type | Updates |
|-----------|---------|----------|------|----------|
| **Minder Core** | v2.1.0 | API Versioning | Ana | Tümü v2.2.0 |
| **FastAPI** | v0.110.0 | Library Versioning | Kütüphane | v0.120.0 |
| **Pydantic** | v2.1.0 | Library Versioning | Kütüphane | v2.2.0 |
| **HTTPX** | v0.26.0 | Library Versioning | Kütüphane | v0.28.0 |
| **AsyncPG** | v0.29.0 | Library Versioning | Kütüphane | v0.30.0 |
| **Redis** | v5.0.0 | Library Versioning | Kütüphane | v5.1.0 |
| **Qdrant** | v1.8.0 | Library Versioning | Kütüphane | v1.10.0 |
| **Neo4j** | v4.4.0 | Library Versioning | Kütüphane | v5.0.0 |
| **Ollama** | v0.5.7 | Library Versioning | Kütüphane | v0.5.8 |

---

**Last Updated:** 2026-04-28
**Version Strategy:** Strategy 2 (Ayrı Versiyonlama)
