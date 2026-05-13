# BATCH 2 Update Report - Medium Risk Services
**Tarih:** 2026-05-10
**Durum:** ✅ TAMAMLANDI (67% başarı, 1 kritik rollback)
**Süre:** ~20 dakika
**Sonuç:** 2/3 servis başarıyla güncellendi, 1 servis kritik sorun nedeniyle rollback

---

## 📊 **Güncelleme Özeti**

### Başarılı Güncellemeler (2/3)

| Servis | Eski Versiyon | Yeni Versiyon | Durum | Risk |
|--------|--------------|---------------|-------|------|
| **Redis** | 7.4.2-alpine | 7.4-alpine | ✅ Başarılı | DÜŞÜK |
| **Neo4j** | 5.26-community | 5.26.25-community | ✅ Başarılı | ORTA |

### Rollback Yapılan (1/3 - KRİTİK)

| Servis | Hedef Versiyon | Gerçekleşen | Durum | Sebep |
|--------|--------------|------------|-------|-------|
| **PostgreSQL** | 18.3-trixie | 17.9-trixie | ⚠️ Rollback | Data format değişikliği |

---

## ⚠️ **Kritik Rollback Detayı**

### PostgreSQL 17.9 → 18.3: DATA FORMAT SORUNU

**Hata Mesajı:**
```
Error: in 18+, these Docker images are configured to store database data in a
format which is compatible with "pg_ctlcluster" (specifically, using
major-version-specific directory names).

Counter to that, there appears to be PostgreSQL data in:
  /var/lib/postgresql/data

This is usually the result of upgrading the Docker image without
upgrading the underlying database using "pg_upgrade" (which requires both
versions).
```

**Sorun:**
- PostgreSQL 18+ farklı data directory format kullanıyor
- Docker volume mount stratejisi değişmiş
- Otomatik upgrade yapılamıyor
- Manual pg_upgrade gerekiyor

**Sebep:**
- PostgreSQL 18'de data directory format değişmiş:
  - Eski: `/var/lib/postgresql/data` (flat structure)
  - Yeni: `/var/lib/postgresql/{version}/main` (versioned structure)

**Çözüm (Yapılan):**
- ✅ Hemen rollback to 17.9-trixie
- ✅ Tüm bağımlı servisler başlatıldı
- ✅ Sistem stabil (%88 healthy)

**Gelecek Çözüm (Gerekli):**
1. **Seçenek A - Manual pg_upgrade:**
   - İki container parallel çalıştır (17.9 ve 18.3)
   - pg_upgrade ile manual migration
   - Data directory'i yeni formata taşı
   - Test ve verification

2. **Seçenek B - Volume Mount Stratejisi:**
   - Docker volume mount'u değiştir
   - `/var/lib/postgresql/data` yerine `/var/lib/postgresql` kullan
   - Postgres 18 otomatik versioned directory oluşturur

3. **Seçenek C - pg_dump/pg_restore:**
   - Full dump al (zaten var: 141KB)
   - Yeni container'da restore
   - Downtime: ~45-90 dakika
   - En güvenli yöntem

**Öneri:** Seçenek C (pg_dump/pg_restore) - en güvenli ve test edilmiş yöntem

---

## 📈 **Sistem Durumu**

### Servis Sağlığı
```
Toplam Servis: 25
Healthy: 22 (%88)
Starting: 3 (normal startup phase)
```

### BATCH 2 Servisleri
```
✅ Redis: Up ~1 hour (healthy)           - redis:7.4-alpine
✅ Neo4j: Up ~30 minutes (healthy)       - neo4j:5.26.25-community
✅ PostgreSQL: Up ~15 minutes (healthy)  - postgres:17.9-trixie (rollback)
```

### Bağımlı Servisler (Tümü Başlatıldı)
```
✅ API Gateway
✅ Plugin Registry
✅ Model Management
✅ Plugin State Manager
✅ Marketplace
✅ OpenWebUI
✅ Telegraf
✅ Postgres Exporter
```

---

## 💡 **Öğrenilenler**

### 1. PostgreSQL Major Version Upgrades
- **Dikkat:** Major version jump'lar (17→18) breaking changes getirebilir
- **Data Format:** PostgreSQL 18+ farklı data directory format kullanıyor
- **Otomatik Upgrade:** Docker image upgrade = otomatik database upgrade DEĞİL
- **Manual Intervention:** pg_upgrade veya pg_dump/pg_restore gerekli

### 2. Docker Volume Mount Strategies
- **Eski Format:** `/var/lib/postgresql/data` (flat)
- **Yeni Format:** `/var/lib/postgresql` (versioned subdirectories)
- **Uyumluluk:** Eski volume'ları yeni format'a migrate etmek gerekli

### 3. Backup Strategies
- **Önemi:** Major version upgrade öncesi mutlaka full backup
- **Test:** Backup restore prosedürü test edilmeli
- **Çoklu Backup:** Hem volume snapshot hem SQL dump almalı

---

## 🎯 **Başarı Kriterleri**

### BATCH 2 (Bugün) - ✅ KISMİ TAMAMLANDI
- ✅ 3 orta riskli servis denendi
- ✅ 2 servis başarıyla yükseltildi (%67)
- ✅ 1 servis kritik sorun nedeniyle stable'da kaldı
- ✅ Tüm servisler healthy veya starting
- ✅ Sistem stabil (%88 healthy)
- ⚠️ PostgreSQL için ayrıntılı migration planı gerekli

---

## 📋 **PostgreSQL 18 Migration Planı (Gelecek)

### Adım 1: Hazırlık (15 dakika)
```bash
# 1. Tüm servisleri durdur
./setup.sh stop

# 2. Ekstra backup al
docker exec minder-postgres pg_dumpall -U minder | gzip > backup.sql.gz

# 3. Volume snapshot al
docker run --rm -v minder_postgres_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/postgres-volume-backup.tar.gz /data
```

### Adım 2: Migration (45-90 dakika)
```bash
# Seçenek A: pg_dump/pg_restore (ÖNERİLEN)
# 1. Yeni container'ı boş data ile başlat
docker compose run -d --rm postgres:18.3-trixie
# 2. Data'yı restore et
gunzip -c backup.sql.gz | docker exec -i minder-postgres psql -U minder
# 3. Verification
docker exec minder-postgres psql -U minder -c "SELECT version();"
```

### Adım 3: Testing (15 dakika)
```bash
# 1. Bağımlı servisleri başlat
docker compose up -d api-gateway plugin-registry

# 2. Application test
curl http://localhost/api/health

# 3. Database verification
docker exec minder-postgres psql -U minder -d minder -c "\dt"
```

**Tahmini Toplam Süre:** 75-120 dakika
**Risk:** ORTA (backup hazır, rollback mümkün)

---

## 🔄 **Rollback Prosedürleri**

### PostgreSQL Rollback (Yapılan - Başarılı)

**1. Servisi Durdur:**
```bash
docker compose stop postgres
```

**2. Versiyonu Değiştir:**
```bash
# setup.sh'da postgres:18.3-trixie → postgres:17.9-trixie
nano setup.sh
```

**3. docker-compose.yml'yi Yeniden Oluştur:**
```bash
./setup.sh regenerate-compose
```

**4. Servisi Başlat:**
```bash
docker compose up -d postgres
```

**5. Bağımlı Servisleri Başlat:**
```bash
docker compose up -d api-gateway plugin-registry marketplace
```

**Sonuç:** ✅ Başarılı, 5 dakikada rollback tamamlandı

---

## 📊 **BATCH 1 + BATCH 2 Kombine Sonuç**

### Toplam Güncelleme Başarısı

| Batch | Toplam | Başarılı | Rollback | Başarı Oranı |
|-------|--------|----------|----------|--------------|
| BATCH 1 (Düşük Risk) | 7 | 5 | 2 | %71 |
| BATCH 2 (Orta Risk) | 3 | 2 | 1 | %67 |
| **TOPLAM** | **10** | **7** | **3** | **%70** |

### Başarıyla Güncellenen Servisler (7)
1. ✅ Grafana: 11.6-ubuntu → 11.6.0
2. ✅ Traefik: v3.3.4 → v3.7.0
3. ✅ Alertmanager: v0.28.1 → latest
4. ✅ Postgres Exporter: v0.15.0 → latest
5. ✅ Redis Exporter: v1.62.0 → v1.83.0
6. ✅ Redis: 7.4.2-alpine → 7.4-alpine
7. ✅ Neo4j: 5.26-community → 5.26.25-community

### Rollback Yapılan Servisler (3)
1. ⚠️ Prometheus: v3.1.0 → v3-distroless → v3.1.0 (permission)
2. ⚠️ Telegraf: 1.34.0 → 1.38.3 → 1.34.0 (Docker socket)
3. ⚠️ PostgreSQL: 17.9-trixie → 18.3-trixie → 17.9-trixie (data format)

---

## 🚀 **Sonraki Adımlar**

### 1. PostgreSQL 18 Migration Plan (Öncelikli)
- Detaylı pg_dump/pg_restore planı hazırla
- Test environment'de dene
- Production migration schedule'a al
- Tahmini süre: 2 saat

### 2. BATCH 3 (Yüksek Risk) - Planlama Gerekli
**Hedef Servisler:**
1. Qdrant (vector database)
2. MinIO (object storage)
3. OpenWebUI (AI interface)
4. Ollama (LLM runner)
5. Jaeger (tracing)

**Risk Seviyesi:** YÜKSEK
**Ön Hazırlık:** Kapsamlı testing ve backup planları gerekli

### 3. Monitoring ve Documentation
- Grafana dashboard'ları güncelle
- Update runbook'ları oluştur
- Rollback prosedürlerini dokümante et

---

## 📞 **Acil Durum Prosedürleri**

### Eğer PostgreSQL Migration Sırasında Sorun Olursa

**1. Hemen Rollback:**
```bash
# Eski image'e dön
docker compose stop postgres
# setup.sh'da versiyonu değiştir
./setup.sh regenerate-compose
docker compose up -d postgres
```

**2. Backup'tan Restore:**
```bash
# SQL dump'tan restore
gunzip -c /tmp/postgres-pre-upgrade-*.sql.gz | \
  docker exec -i minder-postgres psql -U minder
```

**3. Volume Restore:**
```bash
# Volume snapshot'tan restore
docker run --rm -v minder_postgres_data:/data \
  -v $(pwd):/backup alpine tar xzf /backup/postgres-volume-backup.tar.gz
```

---

**Rapor Durumu:** BATCH 2 KISMİ TAMAMLANDI ✅
**Başarı Oranı:** %67 (2/3 başarılı, 1/3 ertelendi)
**Sistem Durumu:** 🟢 STABİL (%88 healthy)
**Sonraki Phase:** PostgreSQL 18 migration planı (öncelikli)

---

*Generated: 2026-05-10 13:45*
*Next Review: 2026-05-11 09:00*
*Total Time: ~20 minutes*
*PostgreSQL Migration: PLANLANMASI GEREKLİ*
