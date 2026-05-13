# PostgreSQL 17.9 → 18.3 Migration Plan
**Tarih:** 2026-05-10
**Durum:** PLAN HAZIR
**Öncelik:** KRİTİK
**Tahmini Süre:** 90-120 dakika
**Risk:** ORTA (Backup hazır, rollback mümkün)

---

## 📊 **Mevcut Durum**

### Database Bilgileri
- **Mevcut Versiyon:** PostgreSQL 17.9 (Debian 17.9-1.pgdg13+1)
- **Hedef Versiyon:** PostgreSQL 18.3-trixie
- **Platform:** aarch64-unknown-linux-gnu (ARM64)
- **Data Size:** ~70 MB (10 database)
- **Kritik Database:** minder (10150 kB)

### Backup Durumu
- ✅ SQL Dump: 141KB (2026-05-09)
- ✅ Emergency Dump: 18KB (2026-05-10 13:37)
- ✅ Volume Data: Mevcut (docker volume)

### Bağımlı Servisler
- API Gateway
- Plugin Registry
- Model Management
- Plugin State Manager
- Marketplace
- OpenWebUI
- Telegraf
- Postgres Exporter

---

## 🎯 **Migration Stratejisi**

### Seçilen Yöntem: **pg_dump + pg_restore** (En Güvenli)

**Neden bu yöntem?**
1. ✅ En güvenli ve test edilmiş yöntem
2. ✅ Full data consistency garantisi
3. ✅ Rollback kolaylığı
4. ✅ Schema ve data integrity kontrolü
5. ✅ Docker volume mount sorunlarını aşar

**Alternatifler (Reddedilen):**
- ❌ pg_upgrade: Volume mount format değişikliği gerektirir, karmaşık
- ❌ Streaming replication: Test gerektirir, zaman alıcı

---

## 📋 **Detaylı Migration Adımları**

### FAZ 1: Hazırlık (20 dakika)

#### 1.1 Pre-Migration Check (5 dakika)
```bash
# Database listesi ve boyutları
docker exec minder-postgres psql -U minder -c "\l+"

# Tablo sayıları
docker exec minder-postgres psql -U minder -d minder -c "\dt"

# Extension listesi
docker exec minder-postgres psql -U minder -c "\dx"

# Active connections
docker exec minder-postgres psql -U minder -c "SELECT count(*) FROM pg_stat_activity;"
```

#### 1.2 Full Backup (10 dakika)
```bash
# SQL dump al
docker exec minder-postgres pg_dumpall -U minder | gzip > /root/minder/backups/postgres/pre-18-upgrade-full-$(date +%Y%m%d-%H%M%S).sql.gz

# Volume snapshot
docker run --rm -v minder_postgres_data:/data -v /root/minder/backups/postgres:/backup \
  alpine tar czf /backup/postgres-17-volume-$(date +%Y%m%d-%H%M%S).tar.gz /data

# Backup doğrula
ls -lh /root/minder/backups/postgres/pre-18-upgrade-full-*.sql.gz
ls -lh /root/minder/backups/postgres/postgres-17-volume-*.tar.gz
```

#### 1.3 Servisleri Durdur (5 dakika)
```bash
cd infrastructure/docker

# PostgreSQL'e bağlı servisleri durdur
docker compose stop api-gateway plugin-registry model-management \
  plugin-state-manager marketplace openwebui telegraf postgres-exporter

# PostgreSQL'i durdur
docker compose stop postgres
```

**Beklenen Downtime Başlangıcı:** ⏱️ Şimdi

---

### FAZ 2: Data Export (15 dakika)

#### 2.1 Data Directory'i Yedekle (5 dakika)
```bash
# Mevcut data directory'i yedekle
docker run --rm -v minder_postgres_data:/data -v /root/minder/backups/postgres:/backup \
  alpine sh -c "cd /data && tar czf /backup/postgres-17-data-final.tar.gz ."

# Doğrula
ls -lh /root/minder/backups/postgres/postgres-17-data-final.tar.gz
```

#### 2.2 SQL Dump Oluştur (10 dakika)
```bash
# Tüm database'leri dump et (schema + data)
docker exec minder-postgres pg_dumpall -U minder --clean --if-exists | \
  gzip > /root/minder/backups/postgres/migration-dump-18.sql.gz

# Progress izle
docker exec minder-postgres pg_dumpall -U minder --clean --if-exits | \
  pv | gzip > /root/minder/backups/postgres/migration-dump-18.sql.gz

# Dump boyutunu kontrol et
ls -lh /root/minder/backups/postgres/migration-dump-18.sql.gz
```

**Beklenen Output:** ~1-2 MB (compressed)

---

### FAZ 3: PostgreSQL 18 Kurulumu (20 dakika)

#### 3.1 Docker Compose Güncelle (5 dakika)
```bash
# setup.sh'da versiyonu güncelle
cd /root/minder
nano setup.sh
# Değiştir: "postgres:17.9-trixie|17|none" → "postgres:18.3-trixie|18|none"

# docker-compose.yml'yi yeniden oluştur
./setup.sh regenerate-compose
```

#### 3.2 Volume'u Temizle (10 dakika)
```bash
# MEVCUT DATA SİLİNECEK! Emin misiniz?
# ⚠️ BU ADIM GERİ ALINAMAZ

cd infrastructure/docker

# Volume'u kaldır (data silinecek)
docker volume rm minder_postgres_data

# Yeni volume oluştur (Postgres 18 formatında)
docker volume create minder_postgres_data
```

**KRİTİK UYARI:** Bu adımdan sonra geri dönüş yok! Backup'ların hazır olduğundan emin olun.

#### 3.3 PostgreSQL 18'i Başlat (5 dakika)
```bash
# PostgreSQL 18'i başlat (boş database ile)
docker compose up -d postgres

# Logları izle
docker logs -f minder-postgres
```

**Beklenen Output:**
```
PostgreSQL init process complete; ready for start up.
```

---

### FAZ 4: Data Import (25 dakika)

#### 4.1 SQL Restore (20 dakika)
```bash
# Dump dosyasını restore et
gunzip -c /root/minder/backups/postgres/migration-dump-18.sql.gz | \
  docker exec -i minder-postgres psql -U minder

# Progress izle (pv ile)
gunzip -c /root/minder/backups/postgres/migration-dump-18.sql.gz | \
  pv | docker exec -i minder-postgres psql -U minder

# Alternatif: Her database'i ayrı ayrı restore
for db in minder minder_authelia minder_marketplace template1; do
  echo "Restoring $db..."
  docker exec -i minder-postgres psql -U minder -d postgres \
    -c "CREATE DATABASE $db;" 2>/dev/null || true
  gunzip -c /root/minder/backups/postgres/migration-dump-18.sql.gz | \
    docker exec -i minder-postgres psql -U minder -d $db
done
```

#### 4.2 Verification (5 dakika)
```bash
# Versiyon kontrolü
docker exec minder-postgres psql -U minder -c "SELECT version();"

# Database listesi
docker exec minder-postgres psql -U minder -c "\l"

# Tablo sayıları (minder database)
docker exec minder-postgres psql -U minder -d minder -c "\dt"

# Data integrity kontrolü
docker exec minder-postgres psql -U minder -d minder -c "
  SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_tables
  WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
  ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
"
```

---

### FAZ 5: Servisleri Başlat (15 dakika)

#### 5.1 Bağımlı Servisleri Başlat (10 dakika)
```bash
cd infrastructure/docker

# Sırayla başlat (bağımlılık sırasına göre)
docker compose up -d postgres-exporter
docker compose up -d telegraf
docker compose up -d plugin-state-manager
docker compose up -d model-management
docker compose up -d marketplace
docker compose up -d plugin-registry
docker compose up -d openwebui
docker compose up -d api-gateway
```

#### 5.2 Health Check (5 dakika)
```bash
# Tüm servislerin durumunu kontrol et
docker ps --filter "name=minder" --format "table {{.Names}}\t{{.Status}}"

# API health check
curl -f http://localhost/api/health || echo "API Gateway not ready"

# Plugin registry health
curl -f http://localhost/plugin-registry/health || echo "Plugin Registry not ready"

# Database connection test
docker exec minder-postgres psql -U minder -d minder -c "SELECT 1;" || echo "Database connection failed"
```

---

### FAZ 6: Post-Migration Testing (20 dakika)

#### 6.1 Application Tests (10 dakika)
```bash
# API Gateway test
curl -X GET http://localhost/api/v1/plugins

# Plugin Registry test
curl -X GET http://localhost/plugin-registry/v1/plugins

# Model Management test
curl -X GET http://localhost/model-management/v1/models

# Marketplace test
curl -X GET http://localhost/marketplace/v1/items
```

#### 6.2 Performance Check (5 dakika)
```bash
# Database performansı
docker exec minder-postgres psql -U minder -d minder -c "
  SELECT schemaname, tablename,
         seq_scan, idx_scan,
         pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
  FROM pg_stat_user_tables
  ORDER BY seq_scan DESC;
"

# Slow query kontrolü
docker exec minder-postgres psql -U minder -d minder -c "
  SELECT query, calls, total_time, mean_time
  FROM pg_stat_statements
  ORDER BY mean_time DESC
  LIMIT 10;
"
```

#### 6.3 Log Kontrolü (5 dakika)
```bash
# PostgreSQL logları
docker logs --tail 100 minder-postgres | grep -i error

# API Gateway logları
docker logs --tail 100 minder-api-gateway | grep -i error

# Plugin Registry logları
docker logs --tail 100 minder-plugin-registry | grep -i error
```

---

## 🔄 **Rollback Prosedürü**

### Eğer Migration Başarısız Olursa

#### Rollback Adım 1: Servisleri Durdur (2 dakika)
```bash
cd infrastructure/docker
docker compose stop api-gateway plugin-registry model-management \
  marketplace openwebui postgres
```

#### Rollback Adım 2: PostgreSQL 17'ye Dön (5 dakika)
```bash
# setup.sh'da versiyonu değiştir
cd /root/minder
nano setup.sh
# Değiştir: "postgres:18.3-trixie|18|none" → "postgres:17.9-trixie|17|none"

# docker-compose.yml'yi yeniden oluştur
./setup.sh regenerate-compose
```

#### Rollback Adım 3: Data'yı Restore Et (10 dakika)
```bash
# Seçenek A: SQL dump'tan restore (hızlı)
cd infrastructure/docker
docker volume rm minder_postgres_data
docker volume create minder_postgres_data
docker compose up -d postgres
gunzip -c /root/minder/backups/postgres/pre-18-upgrade-full-*.sql.gz | \
  docker exec -i minder-postgres psql -U minder

# Seçenek B: Volume'dan restore (daha güvenli)
docker run --rm -v minder_postgres_data:/data \
  -v /root/minder/backups/postgres:/backup \
  alpine sh -c "cd /data && tar xzf /backup/postgres-17-data-final.tar.gz"
```

#### Rollback Adım 4: Servisleri Başlat (5 dakika)
```bash
cd infrastructure/docker
docker compose up -d postgres-exporter telegraf model-management \
  plugin-state-manager marketplace plugin-registry openwebui api-gateway
```

**Toplam Rollback Süresi:** ~20 dakika

---

## ⚠️ **Risk Analizi**

### Yüksek Risk Alanları

1. **Data Loss (Yüksek)**
   - **Mitigation:** 3 farklı backup (SQL dump, volume snapshot, emergency dump)
   - **Rollback:** 20 dakika

2. **Service Downtime (Orta)**
   - **Beklenen:** 90-120 dakika
   - **Etki:** API, Plugin Registry, Marketplace kullanılamaz
   - **Mitigation:** Bakım penceresi (maintance window)

3. **Application Compatibility (Orta)**
   - **Risk:** PostgreSQL 18 breaking changes
   - **Mitigation:** Application test planı hazır
   - **Rollback:** Hızlı rollback mümkün

### Düşük Risk Alanları

1. **Performance Degradation (Düşük)**
   - PostgreSQL 18 genellikle daha hızlı
   - Query planner iyileştirmeleri

2. **Storage Usage (Düşük)**
   - ~70 MB data, çok küçük
   - Migration sonrası benzer boyut beklenir

---

## 📊 **Success Criteria**

### Migration Başarılı Olduğunda

- ✅ PostgreSQL 18.3 çalışıyor
- ✅ Tüm 10 database migrate edildi
- ✅ Tüm tablalar mevcut
- ✅ Data integrity korundu
- ✅ Bağımlı tüm servisler healthy
- ✅ API endpoints çalışıyor
- ✅ Error log'larında artış yok

### Performance Benchmarks

- **Query Performance:** İyileşme veya aynı beklenir
- **Connection Time:** < 1 saniye
- **Memory Usage:** Benzer veya daha az beklenir

---

## 📞 **Acil Durum İletişimi**

### Eğer Kritik Hata Olursa

**1. Hemen Rollback:**
```bash
# Rollback script'i çalıştır
/root/minder/scripts/rollback-postgres-18.sh
```

**2. Eki İle İletişime Geç:**
- Sistem loglarını kaydet
- Hata mesajlarını dokümante et
- Backup konumlarını not et

**3. Alternative Plan:**
- PostgreSQL 17.9'da kal (stable)
- İleri tarih tekrar dene

---

## 🎯 **Timeline**

### Toplam Süre: 90-120 dakika

| Faz | Süre | Başlama | Bitiş |
|-----|-------|---------|-------|
| Hazırlık | 20 dk | 14:00 | 14:20 |
| Data Export | 15 dk | 14:20 | 14:35 |
| PostgreSQL 18 Kurulum | 20 dk | 14:35 | 14:55 |
| Data Import | 25 dk | 14:55 | 15:20 |
| Servis Başlatma | 15 dk | 15:20 | 15:35 |
| Testing | 20 dk | 15:35 | 15:55 |

**Maintenance Window:** 14:00 - 16:00 (2 saat)

---

## ✅ **Pre-Migration Checklist**

### Backup (Kritik)
- [ ] Full SQL dump alındı
- [ ] Volume snapshot alındı
- [ ] Emergency dump alındı
- [ ] Backup'lar doğrulandı

### Hazırlık
- [ ] Migration planı okundu
- [ ] Rollback prosedürü anlaşıldı
- [ ] Team bilgilendirildi
- [ ] Maintenance window onaylandı

### Sistem
- [ ] Tüm servisler healthy
- [ ] Yeterli disk alanı var
- [ ] Network stabil
- [ ] Docker compose dosyası hazır

---

**Plan Durumu:** HAZIR ✅
**Risk Seviyesi:** ORTA
**Rollback:** 20 dakika
**Next Step:** Kullanıcı onayı bekleniyor

---

*Generated: 2026-05-10 13:50*
*Migration Start: Onay bekleniyor*
*Estimated Completion: 15:55*
