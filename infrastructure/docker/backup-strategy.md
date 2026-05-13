# Minder Platform Yedekleme Stratejisi

**Tarih:** 2026-05-07
**Durum:** 🟡 UYGULANACAK
**Öncelik:** Kritik

## 📊 Mevcut Durum

### Eksik Yedekleme
- ❌ Otomatik yedekleme sistemi YOK
- ❌ PostgreSQL dump yok
- ❌ Redis persistence yok
- ❌ Neo4j backup yok
- ❌ Config file version control eksik

### Risk Analizi
**Kritik Veriler:**
1. **PostgreSQL:** Kullanıcı verileri, plugin metadata, licensing
2. **Redis:** Session data, cache, rate limiting state
3. **Neo4j:** Graph database (knowledge graphs)
4. **Config:** Traefik, Authelia, environment variables

## 🎯 Yedekleme Stratejisi

### Seviye 1: Kritik Veriler (Günlük)

#### 1.1 PostgreSQL Yedekleme
**Araç:** `pg_dump` + cron job
**Sıklık:** Günlük (saat 03:00)
**RetentionPolicy:** 7 günlük

```bash
#!/bin/bash
# /root/minder/infrastructure/docker/scripts/backup-postgres.sh

BACKUP_DIR="/backup/postgres"
DATE=$(date +%Y%m%d_%H%M%S)
CONTAINER_NAME="minder-postgres"

# Backup dizini oluştur
mkdir -p "$BACKUP_DIR"

# PostgreSQL dump al
docker exec "$CONTAINER_NAME" pg_dump -U minder -d minder > "$BACKUP_DIR/minder_$DATE.sql"

# Compress
gzip "$BACKUP_DIR/minder_$DATE.sql"

# 7 günden eski yedekleri sil
find "$BACKUP_DIR" -name "minder_*.sql.gz" -mtime +7 -delete

echo "PostgreSQL backup completed: minder_$DATE.sql.gz"
```

**Cron Job:**
```cron
0 3 * * * /root/minder/infrastructure/docker/scripts/backup-postgres.sh >> /var/log/backup.log 2>&1
```

#### 1.2 Redis Yedekleme
**Araç:** Redis RDB snapshot
**Sıklık:** Her 5 dakika (otomatik)
**RetentionPolicy:** 1 günlük

`docker-compose.yml` Redis konfigürasyonu:
```yaml
redis:
  image: redis:7.4-alpine
  command: redis-server --save 300 1 --appendonly yes
  volumes:
    - redis_data:/data
    - ./redis/redis.conf:/usr/local/etc/redis/redis.conf:ro
```

#### 1.3 Neo4j Yedekleme
**Araç:** `neo4j-admin backup`
**Sıklık:** Günlük (saat 04:00)
**RetentionPolicy:** 7 günlük

```bash
#!/bin/bash
# /root/minder/infrastructure/docker/scripts/backup-neo4j.sh

BACKUP_DIR="/backup/neo4j"
DATE=$(date +%Y%m%d_%H%M%S)

# Backup dizini oluştur
mkdir -p "$BACKUP_DIR"

# Neo4j backup al
docker exec minder-neo4j neo4j-admin backup --backup-dir=/backups --from=docker --name="minder_$DATE"

# 7 günden eski yedekleri sil
find "$BACKUP_DIR" -name "minder_*" -mtime +7 -delete

echo "Neo4j backup completed: minder_$DATE"
```

### Seviye 2: Konfigürasyon Yedekleme (Haftalık)

#### 2.1 Config Files Yedekleme
**Araç:** Git commit + rsync
**Sıklık:** Her commit'te + haftalık sync

```bash
#!/bin/bash
# /root/minder/infrastructure/docker/scripts/backup-config.sh

CONFIG_DIR="/backup/config"
DATE=$(date +%Y%m%d_%H%M%S)

# Config dosyalarını yedekle
rsync -av /root/minder/infrastructure/docker/ "$CONFIG_DIR/$DATE/" \
  --exclude='*.log' \
  --exclude='*.pyc' \
  --exclude='__pycache__'

# Environment variables yedekle
cp /root/minder/infrastructure/docker/.env "$CONFIG_DIR/$DATE/.env.backup"

echo "Config backup completed: $DATE"
```

### Seviye 3: Volume Snapshot (Aylık)

#### 3.1 Docker Volume Backup
**Araç:** `docker-volume-backup` script
**Sıklık:** Aylık
**RetentionPolicy:** 3 aylık

```bash
#!/bin/bash
# /root/minder/infrastructure/docker/scripts/backup-volumes.sh

VOLUMES=(
  "postgres_data"
  "redis_data"
  "neo4j_data"
  "openwebui_data"
  "qdrant_storage"
)

BACKUP_DIR="/backup/volumes"
DATE=$(date +%Y%m%d_%H%M%S)

for volume in "${VOLUMES[@]}"; do
  echo "Backing up volume: $volume"
  docker run --rm \
    -v "$volume:/data:ro" \
    -v "$BACKUP_DIR:/backup" \
    alpine tar czf "/backup/${volume}_${DATE}.tar.gz" -C /data .
done

# 3 aydan eski yedekleri sil
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +90 -delete

echo "Volume backup completed: $DATE"
```

## 📋 Uygulama Planı

### Hafta 1: Kritik Yedekleme
- [ ] PostgreSQL backup script oluştur
- [ ] Redis persistence yapılandır
- [ ] Neo4j backup script oluştur
- [ ] Cron job'ları kur

### Hafta 2: Config Yedekleme
- [ ] Config backup script oluştur
- [ ] Environment variables yedekleme
- [ ] Git commit hooks ekle

### Hafta 3: Volume Backup
- [ ] Volume backup script oluştur
- [ ] Test yedekleme/geri yükleme
- [ ] Monitoring/alerting ekle

### Hafta 4: Dokümantasyon ve Test
- [ ] Disaster recovery planı yaz
- [ ] Yedekten geri yükleme test et
- [ ] Yıllık yedekleme stratejisi

## 🔍 Monitoring ve Alerting

### Yedekleme Başarısı Kontrolü
```bash
# Son 24 saatte yedek var mı?
find /backup -name "*.sql.gz" -mtime -1 | grep -q . && echo "✅ PostgreSQL backup mevcut"
find /backup -name "minder_*" -mtime -1 | grep -q . && echo "✅ Neo4j backup mevcut"
```

### Prometheus Alerts
```yaml
# /root/minder/infrastructure/docker/prometheus/rules/backup.rules.yml
groups:
  - name: backup_alerts
    rules:
      - alert: BackupTooOld
        expr: time() - backup_last_success_timestamp_seconds > 86400
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "Yedekleme 24 saatten eski"
```

## 🧪 Test Senaryoları

### Test 1: PostgreSQL Geri Yükleme
```bash
# 1. Test veritabanı oluştur
docker exec -i minder-postgres psql -U minder -c "DROP DATABASE IF EXISTS minder_test; CREATE DATABASE minder_test;"

# 2. Yedeği geri yükle
gunzip -c /backup/postgres/minder_20260507_030000.sql.gz | docker exec -i minder-postgres psql -U minder -d minder_test

# 3. Veri doğrulama
docker exec -i minder-postgres psql -U minder -d minder_test -c "SELECT COUNT(*) FROM users;"
```

### Test 2: Redis Geri Yükleme
```bash
# 1. Redis yedeğini kopyala
docker cp minder-redis:/data/dump.rdb /backup/redis/

# 2. Test Redis container'ı başlat
docker run --name redis-test -v /backup/redis:/data redis:7.4-alpine

# 3. Veri doğrulama
docker exec -it redis-test redis-cli KEYS '*'
```

## 📊 Yedekleme Boyutları

### Tahmini Günlük Artış
- **PostgreSQL:** ~50MB/gün (compressed)
- **Redis:** ~10MB/gün (RDB)
- **Neo4j:** ~100MB/gün
- **Config:** ~5MB/gün
- **Toplam:** ~165MB/gün

### Depolama Gereksinimi (7 günlük)
- **PostgreSQL:** 350MB
- **Redis:** 70MB
- **Neo4j:** 700MB
- **Config:** 35MB
- **Toplam:** ~1.2GB

## 🚀 Acil Eylem Planı

### Bugün Yapılacaklar
1. ✅ Yedekleme stratejisi dokümante et
2. ⏭️ PostgreSQL backup script oluştur ve test et
3. ⏭️ Redis persistence'ı etkinleştir
4. ⏭️ İlk yedekleri al

### Bu Hafta Yapılacaklar
1. Neo4j backup implementasyonu
2. Config yedekleme sistemi
3. Monitoring/alerting kurulumu
4. Disaster recovery documentation

## 💡 Öneriler

### Kısa Vadeli (1-2 Hafta)
- ✅ PostgreSQL günlük yedekleme
- ✅ Redis persistence
- ✅ Yedek monitoring

### Orta Vadeli (1-2 Ay)
- ✅ Neo4j yedekleme
- ✅ Config version control
- ✅ Otomatik geri yükleme testleri

### Uzun Vadeli (3-6 Ay)
- ✅ Cloud backup integration (S3, Azure Blob)
- ✅ Multi-region replication
- ✅ Point-in-time recovery
- ✅ Yıllık arşivleme stratejisi

## 🎯 Başarı Metrikleri

### Kısa Vadeli Hedefler (1 Hafta)
- PostgreSQL yedekleme sistemi aktif
- %100 yedekleme başarı oranı
- < 5 dakika yedekleme süresi

### Uzun Vadeli Hedefler (1-2 Ay)
- Tam otomatik yedekleme sistemi
- Yıllık disaster recovery testi
- RTO < 1 saat, RPO < 5 dakika

## 📞 İletişim ve Sorumluluk

**Yedekleme Sorumlusu:** Sistem Yöneticisi
**Test Sorumlusu:** DevOps Ekipleri
**Onay Sorumlusu:** Platform Lead

---

**Sonraki Adım:** PostgreSQL backup script oluştur ve test et.
