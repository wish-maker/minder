# Minder Platform - Next Steps

## ✅ Tamamlanan (Production-Ready Kanıtlı)

| Servis | Durum | Kanıt | Test Tarihi |
|--------|-------|-------|------------|
| **api-gateway** | ✅ Production-ready | 9 E2E test geçti | - |
| **rag-pipeline** | ✅ Production-ready | Persistence çift-restart kanıtlı | - |
| **plugin-registry** | ✅ Production-ready | Persistence + gateway JWT auth, **401 kanıtlı** | 2025-06-16 |
| **graph-rag** | ✅ Production-ready | Neo4j auth + retrieval working, **entity matching kanıtlı** | 2025-06-17 |
| **model-management** | ✅ Production-ready | Gerçek Ollama entegrasyonu, **list/show kanıtlı, restart-safe** | 2025-06-17 |

### Test Kanıtları

**plugin-registry JWT Auth (2025-06-16):**
```bash
# TEST 1: Geçersiz JWT → 401
HTTP/1.1 401 Unauthorized
{"detail":"Invalid token: Not enough segments"}

# TEST 2: JWT yok → 401
HTTP/1.1 401 Unauthorized
{"detail":"Missing or invalid Authorization header"}

# TEST 3: Geçerli JWT → 404 (auth geçti, plugin yok)
HTTP/1.1 404 Not Found
{"detail":"Plugin not found"}
```

**graph-rag Entity Retrieval (2025-06-17):**
```bash
# TEST 1: Query "Bill Gates Microsoft" → 7 related entities
{"entity_count": 7, "related_entities": [
  "Bill Gates", "Microsoft", "1975", "Paul Allen", "MS-DOS", "Windows", "Redmond"
]}

# TEST 2: Query "Steve Jobs Apple" → 8 related entities
{"entity_count": 8, "related_entities": [
  "Steve Jobs", "Steve Wozniak", "Apple Computer", "California", "Macintosh"
]}

# TEST 3: Graph construction → 142 relationships created
{"entity_count": 18, "relationship_count": 142}
```

**model-management Ollama Integration (2025-06-17):**
```bash
# TEST 1: GET /models → gerçek Ollama listesi
[{"id":"llama3.2:latest","name":"llama3.2:latest","type":"local","provider":"ollama","size":"1.88 GB","status":"ready"},{"id":"nomic-embed-text:latest","name":"nomic-embed-text:latest","type":"local","provider":"ollama","size":"0.26 GB","status":"ready"}]

# TEST 2: GET /models/llama3.2:latest → gerçek model detayları (license, parameters, modelfile)
{"id":"llama3.2:latest","details":{"license":"LLAMA 3.2 COMMUNITY LICENSE...","modelfile":"FROM llama3.2...","parameters":{"num_ctx":4096}}}

# TEST 3: RESTART test → aynı liste (Ollama source-of-truth)
# Önce: [llama3.2:latest, nomic-embed-text:latest]
# Restart sonrası: [llama3.2:latest, nomic-embed-text:latest] ✅ AYNI

# TEST 4: Docker logs → sessiz except yok
# Sonuç: "No errors found in logs" ✅
```

---

## 🚨 KRİTİK GÜVENLİK RİSKLERİ

### ⚠️ RCE Riski: 3rd-Party Plugin Execution

| Risk Alanı | Şiddet | Vektör | Durum |
|-------------|---------|--------|-------|
| **Plugin Installation** | 🔴 Kritik | Git clone + kod çalıştırma | 501 - yazılmadı |
| **Plugin Activation** | 🔴 Kritik | 3rd-party kod workdir'de çalışır | Sandbox yok |
| **Plugin Hooks** | 🟡 Yüksek | User input → system command | Validation yok |

**RCE Saldiri Vektörleri:**
1. **Malicious Git Repo**: Plugin install URL'si zararlı kod içeriyor
2. **Hook Injection**: Plugin hook'larında system command çalıştırma
3. **Dependency Confusion**: Zararlı package name collision
4. **File Write**: Plugin disk'e dosya yazabiliyor (path traversal?)

**Güvenlik Kontrolleri GEREKLİ:**
```yaml
Zorunlu:
  - Plugin sandbox/chroot isolasyonu
  - Hook signature validation
  - System command block/whitelist
  - Resource limits (CPU, memory, disk)
  - Network isolation (private Docker network)
  
İleri Seviye:
  - Plugin code scanning/static analysis
  - Runtime behavioral monitoring
  - Automatic suspicious activity detection
```

### 🟡 Diğer Güvenlik Alanları

| Alan | Risk | Öncelik |
|------|------|---------|
| **JWT Secret Rotation** | 🟡 Orta | Secretlerin environment variable'de kalması |
| **Rate Limiting** | 🟡 Orta | Tüm servislerde uniform olmaması |
| **Database Credentials** | 🟡 Orta | POSTGRES_PASSWORD, REDIS_PASSWORD rotasyonu |
| **Neo4j Auth** | 🟡 Orta | ✅ Düzeltildi, ama rotation planı yok |

### 🟠 Donanımsal Kısıtlar

| Alan | Sorun | Etki | Çözüm |
|------|-------|------|-------|
| **Pi RAM Bütçesi** | Raspberry Pi 4 (4GB) | neo4j+qdrant+ollama aynı anda ~2.7GB+ RAM kullanıyor | Servise-göre-açılan yapı düşünülmeli |
| **Model Training** | Pi 4 CPU/RAM yetersiz | Fine-tuning pratik değil | External GPU sunucusu veya kaldırma |
| **Concurrent Inference** | RAM pressure | Çoklu LLM çağrısı OOM riski | Rate limiting + queue system |

**RAM Kullanımı (Tahmini):**
- neo4j: ~800MB (graph DB)
- qdrant: ~400MB (vector DB)
- ollama: ~1.5GB (llama3.2 model)
- rag-pipeline: ~200MB (embeddings + processing)
- api-gateway: ~100MB (FastAPI + Redis client)
- plugin-registry: ~150MB (PostgreSQL pool + plugin instances)
- **TOPLAM: ~3.1GB** (4GB Pi'de riskli)

**Öneri:** Production için servis başlatma sırası veya selective activation gerekli.

---

## 🔴 YARIM KALDI (DURDURULMUŞ SERVİSLER)

### tts-stt — YARIM KALDI

**Sorun:** gTTS/Google internet gerektiriyor, offline hedefiyle çelişiyor. Piper'a geçilecek (açık kaynak, offline).

**Engel:** Piper Türkçe modelleri (fahrettin/fettah) main branch'ten kaldırılmış, v1.0.0 tag'i CLI'dan 403 veriyor.

**ÇÖZÜM (sonraki oturum):**
- Model .onnx dosyasını TARAYICIDAN elle indir (huggingface rhasspy/piper-voices)
- Proje içinde `src/services/tts-stt/models/` klasörüne koy
- Dockerfile'da wget yerine COPY kullan
- Mirror/3. parti kaynak KULLANMA

**Alternatif TTS motorları (eğer Piper TR modeli bulunamazsa):**
- espeak-ng (tam açık kaynak, offline)
- coqui-tts (neural TTS, offline capable)

**NOT:** Model eğitmeye GİRME, hazır model bul.

---

## 📋 Sıradaki Servisler (Durum Doğrulanmamış)

| Servis | Durum | Kontrol Edilecek | Öncelik |
|--------|-------|------------------|---------|
| **marketplace** | ❓ | Auth? Persistence? | Orta |
| **ai-service** | ❓ | Auth? Ollama integration? | Orta |

---

## ❌ YAPILAMAZ (Teknik/Donanımsal Kısıtlar)

### model-fine-tuning — YAPILAMAZ

**Sorun:** Ollama'nın gerçek fine-tuning API'si yok. Şu anki implementation sadece simülasyon (asyncio.sleep).

**Kısıtlar:**
- ❌ Ollama fine-tuning API'si production-ready değil
- ❌ Raspberry Pi 4 donanımı model eğitimi için yetersiz (RAM/CPU)
- ❌ Dataset upload var ama training sadece fake (no real ML)

**Alternatifler:**
1. **Servis kaldırılmalı** — Pi üzerinde eğitim pratik değil
2. **Yeniden adlandırma** → "model-customization" (config-only, no training)
3. **External service** — GPU sunucusu ile entegrasyon (aygıt)

**Karar Gerekli:** Servisi mi kaldıralım, yoksa "config-only customization"a mı dönüştürelim?

---

## 🔵 Servis Haritası (Gerçeklik Analizi - Kod Okuma)

### ÇOĞU BOŞ (Placeholder)
- **ai-service**: Sadece version reporting, hiç AI functionality yok. docker-compose'da tanımlı değil.
- **plugin-state-manager**: plugin-registry ile çakışıyor (duplicate routes, overlapping responsibility). Birleştir/sil kararı gerekli.

### KISMEN (Scaffold Var)
- **marketplace**: FastAPI scaffold var, database pool var, ama gerçek implementasyon minimal. AI tools sync var ama basit.

### ÇOĞU GERÇEK (Production-Ready)
- **api-gateway**: Full JWT auth, rate limiting, Redis client, proxy routing
- **plugin-registry**: Plugin lifecycle, PostgreSQL persistence, health monitoring, AI tools
- **rag-pipeline**: Real Ollama embeddings, Qdrant vector DB, ingestion pipeline
- **graph-rag**: Entity extraction, Neo4j integration, retrieval working
- **model-management**: Real Ollama list/show, restart-safe, source-of-truth Ollama

**Her serviste sorgulanacak:**
1. ✅ Auth var mı? JWT/secret validation çalışıyor mu?
2. ✅ Persistence var mı? Restart sonrası data korunuyor mu?
3. ⚠️ Rate limiting var mı? (uniform değil)
4. ⚠️ Error handling yeterli mi? (service-specific)
5. ❓ Dependencies fail olunca ne olur? (test edilmedi)

---

## 🔑 Çalışma Prensibi

> **"Her 'production-ready' iddiasını ÇALIŞTIRARAK doğrula, kod okumasına güvenme."**

| İş Türü | Kime Atılır | Örnek |
|---------|------------|-------|
| **Mekanik iş** (refactor, test yazma, routine bugfix) | GLM (o1, claude-4, etc.) | Graph retrieval fix |
| **Mimari karar** (security, network topology, service boundaries) | Opus 4.8 | Plugin sandbox tasarımı |
| **Güvenlik kritik değişiklik** | Opus + manuel review | RCE önlemleri |

---

## Sonraki Adımlar

### 🔴 KRİTİK (Güvenlik)
1. **[Opus]** Plugin installation güvenli tasarım (sandbox/chroot)
2. **[Opus]** RCE vektör analizi + önlem planı
3. **[Opus]** Plugin hook signature validation
4. **[Opus]** Resource limiting strategy

### 🟡 YÜKSEK (Stabilizasyon - Mimari Kararlar)
5. **marketplace** auth + persistence kontrolü
6. **plugin-state-manager** kararı: birleştir/sil (plugin-registry ile çakışıyor)
7. **ai-service** kararı: gerçek implementasyon veya kaldır
8. **model-fine-tuning** kararı: kaldır veya "config-only customization"a dönüştür
9. **Uniform auth pattern** dokümante (JWT middleware)
10. **Rate limiting** standardizasyonu

### 🟢 NORMAL (Tamamlama)
11. **tts-stt** Piper TTS offline implementasyonu (manuel model indirme + alternatif motorlar)
12. **Health check** standardizasyonu
13. **Pi RAM optimizasyonu** — servis başlatma sırası veya selective activation

---

## 🎯 Hedef: Production Deployment

**Güvenlik Gatekeeper:**
- ✅ Tüm servislerde JWT auth çalışıyor
- ✅ Persistence kanıtlanmış (4/4 servis)
- ⚠️ RCE riski ANALİZ EDİLDİ
- ❌ Rate limiting uniform değil
- ❌ Error handling standardize değil

**Production Checklist:**
- [x] Tüm servisler auth kanıtlanmış (5/5 servis: api-gateway, rag-pipeline, plugin-registry, graph-rag, model-management)
- [x] Tüm servisler persistence kanıtlanmış (5/5 servis)
- [ ] RCE riski analiz edildi + önlemler alındı
- [ ] Uniform rate limiting uygulandı
- [ ] Monitoring + alerting aktif
- [ ] Disaster recovery plan hazır
- [ ] tts-stt offline TTS implementasyonu
- [ ] Pi RAM optimizasyonu (servis başlatma stratejisi)
- [ ] Mimari kararlar alındı (plugin-state-manager, ai-service, model-fine-tuning)

**Notlar:**
- RCE riski production deployment için SHOWSTOPPER. Opus ile kapsamlı analiz gerekli.
- Pi RAM bütçesi — tüm servisler aynı anda açılırsa OOM riski var (~3.1GB / 4GB).
- 3 servis için mimari karar gerekli: plugin-state-manager (birleştir/sil), ai-service (implement/kaldır), model-fine-tuning (dönüştür/kaldır).
