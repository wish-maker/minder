# Minder Platform - Güncelleme Rehberi

**Version:** 1.0.0  
**Last Updated:** 2026-05-10  
**Status:** Production Ready

---

## 📋 Güncelleme Stratejisi

### Risk Kategorileri

Minder platform güncellemeleri 3 risk kategorisine ayrılır:

#### 🟢 Düşük Risk (Monitoring & Exporter'ler)
- **Servisler:** Prometheus, Grafana, Telegraf, Alertmanager, Exporter'ler
- **Risk:** Minimal
- **Etki:** Monitoring only, core işlevsiz
- **Strateji:** Hemen güncelle, health check sufficient

#### 🟡 Orta Risk (Database & AI Services)
- **Servisler:** PostgreSQL, Neo4j, Qdrant, Ollama, Redis
- **Risk:** Orta
- **Etki:** Data persistence, AI functionality
- **Strateji:** Backup al → Test et → Production update

#### 🔴 Yüksek Risk (Core Infrastructure)
- **Servisler:** Traefik, API Gateway, Core microservices
- **Risk:** Yüksek
- **Etki:** Service availability, user impact
- **Strateji:** Canary deployment → Blue-green → A/B testing

---

## 🔄 Güncelleme Adımları

### 1. Pre-Update Checklist

```bash
# 1.1 System health check
./setup.sh status

# 1.2 Backup verification
ls -lh /root/minder/backups/
# Expected: Neo4j (~517MB), PostgreSQL (~141KB), System (~140MB)

# 1.3 Disk space check
df -h /root/minder
# Minimum: 10GB free

# 1.4 Update check
./setup.sh update --check
# Review available updates
```

### 2. Backup Oluşturma

```bash
# 2.1 Full system backup
./setup.sh backup

# 2.2 Verify backup integrity
ls -lh /root/minder/backups/minder-*/
cat /root/minder/backups/minder-*/BACKUP-INFO.txt

# 2.3 Backup offload (optional)
# Copy backup to remote location for disaster recovery
```

### 3. Güncelleme Uygulaması

#### 3.1 Low-Risk Updates (Batch 1)
```bash
# Monitoring & Exporter'ler
./setup.sh update grafana prometheus telegraf alertmanager
./setup.sh update postgres-exporter redis-exporter rabbitmq-exporter

# Health check
./setup.sh status

# Monitoring dashboard kontrol et
# Grafana: http://localhost:3000
# Prometheus: http://localhost:9090
```

#### 3.2 Medium-Risk Updates (Batch 2)
```bash
# Database güncellemeleri (ÖNEMLİ: Backup kontrol!)
./setup.sh update postgres neo4j qdrant redis

# Post-update verification
docker logs minder-postgres | tail -50
docker logs minder-neo4j | tail -50
docker logs minder-qdrant | tail -50
docker logs minder-redis | tail -50

# Data integrity check
# (Database-specific commands)
```

#### 3.3 High-Risk Updates (Batch 3)
```bash
# Core infrastructure (CANARY DEPLOYMENT)
./setup.sh update traefik api-gateway plugin-registry

# Canary monitoring
# - Monitor error rates
# - Check response times
# - Verify business logic
# - A/B testing if needed

# Full rollout
./setup.sh update marketplace plugin-state-manager rag-pipeline
```

### 4. Post-Update Verification

```bash
# 4.1 Health check
./setup.sh status

# 4.2 Service endpoint test
curl -f http://localhost:8000/health || echo "API Gateway FAIL"
curl -f http://localhost:8001/health || echo "Plugin Registry FAIL"
curl -f http://localhost:8002/health || echo "Marketplace FAIL"

# 4.3 Monitoring dashboard review
# Grafana: http://localhost:3000
# Check for anomalies

# 4.4 Log review
docker logs --tail 100 minder-api-gateway | grep -i error
docker logs --tail 100 minder-plugin-registry | grep -i error
```

---

## 🚨 Rollback Prosedürü

### Rollback Kararı Ağacı

```
Sorun Tespit Edildi
    │
    ├─ Kritik mi? (Service down, data loss)
    │   │
    │   ├─ EVET → İM MedYA Rollback
    │   └─ HAYIR → Aşağıya devam et
    │
    ├─ Kullanıcı etkisi var mı?
    │   │
    │   ├─ EVET → 15 dakika içinde rollback
    │   └─ HAYIR → Monitor et + patch hazırla
    │
    └─ Workaround mevcut mu?
        │
        ├─ EVET → Workaround uygula + patch
        └─ HAYIR → Rollback
```

### Rollback Adımları

#### 1. Servis Rollback
```bash
# 1.1 Etkilen servisi durdur
docker stop minder-<service-name>

# 1.2 Eski image tag'ine dön
# docker-compose.yml'de image tag'ini değiştir
# veya
docker tag <new-image> <old-image>

# 1.3 Servisi restart et
docker start minder-<service-name>

# 1.4 Health check
./setup.sh status | grep <service-name>
```

#### 2. Database Rollback
```bash
# 2.1 Servisi durdur
docker stop minder-<database>

# 2.2 Backup'tan restore
# PostgreSQL
cat /root/minder/backups/postgres/manual-*/full-backup-*.sql | \
  docker exec -i minder-postgres psql -U minder

# Neo4j
docker cp /root/minder/backups/neo4j/manual-*/data/. \
  minder-neo4j:/data/

# 2.3 Servisi başlat
docker start minder-<database>

# 2.4 Verify data integrity
# (Database-specific verification)
```

#### 3. System Rollback
```bash
# 3.1 Tüm servisleri durdur
./setup.sh stop

# 3.2 Backup'tan restore
./setup.sh restore /root/minder/backups/minder-<timestamp>/

# 3.3 Servisleri başlat
./setup.sh start

# 3.4 Verify system health
./setup.sh status
```

---

## 📊 Update İzleme

### Update Checklist

| Adım | Durum | Notlar |
|------|--------|--------|
| Pre-update checks | ⬜ | |
| Backup oluştur | ⬜ | |
| Update check | ⬜ | |
| Low-risk updates | ⬜ | |
| Medium-risk updates | ⬜ | |
| High-risk updates | ⬜ | |
| Post-update verification | ⬜ | |
| Monitoring review | ⬜ | |

### Update Log Template

```markdown
## Update Log - YYYY-MM-DD

### Güncellenen Servisler
- [ ] grafana: 11.6 → 13.1.0
- [ ] traefik: v3.3.4 → v3.7.0
- [ ] ...

### Sorunlar
- [ ] Sorun açıklaması
  - Çözüm: ...

### Rollback
- [ ] Rollback yapıldı mı?
  - Sebep: ...
```

---

## ⚠️ Yaygın Sorunlar ve Çözümleri

### Sorun: Update Check Timeout
**Belirtiler:** `./setup.sh update --check` 2+ dakika sürüyor

**Çözüm:**
```bash
# Cache temizle
rm -rf /root/minder/.cache/tags/*

# Tekrar dene
./setup.sh update --check
```

### Sorun: Image Pull Timeout
**Belirtiler:** Docker image çekme başarısız

**Çözüm:**
```bash
# Manuel olarak image çek
docker pull <image>:<tag>

# Tekrar dene
./setup.sh update <service>
```

### Sorun: Container Start Failure
**Belirtiler:** Container başlamıyor

**Çözüm:**
```bash
# Log kontrol et
docker logs <container-name>

# Config diff kontrol et
docker diff <container-name>

# Rollback değerlendir
./setup.sh update <service> --rollback
```

---

## 📞 Destek

### Acil Durumlar
- **Service Down:** İlk olarak `./setup.sh status` çalıştır
- **Data Loss:** Hemen backup'tan restore et
- **Security Issue:** Servisi durdur, security team'e bildir

### Normal Destek
- **Planlı Güncellemeler:** İş saatleri içinde
- **Sorun Giderme:** Bu dökümanı referans al
- **Improvement Önerileri:** Issue tracker üzerinden

---

**Not:** Bu rehber Minder platform güncellemeleri için standart prosedürleri içerir. Her güncelleme öncesi bu rehberi gözden geçirin.

