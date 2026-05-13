# Phase 3: Monitoring Dashboard ve Dokümantasyon
**Tarih:** 2026-05-10
**Durum:** 🟡 BAŞLANGIÇ
**Öncelik:** Sistem gözlemlenebilirliği

---

## 🎯 Phase 3 Hedefleri

### 3.1 Monitoring Dashboard Kurulumu
**Amaç:** Sistem performansını gerçek zamanlı takip et

**Grafana Dashboard'ları:**
1. **System Overview Dashboard**
   - CPU, Memory, Disk usage
   - Network I/O
   - Container health status

2. **Service Health Dashboard**
   - API Gateway metrics
   - Database connection pool
   - Cache hit rates
   - Response times

3. **Application Performance Dashboard**
   - Request throughput
   - Error rates
   - Latency percentiles
   - Business metrics

**Implementation:**
```bash
# 1. Dashboard dizini oluştur
mkdir -p /root/minder/infrastructure/docker/grafana/dashboards

# 2. Prometheus data source konfigürasyonu
# 3. Dashboard JSON dosyalarını import et
# 4. Grafana'da dashboard'ları aktifleştir
```

### 3.2 Alert Kuralları
**Amaç:** Kritik sorunlarda otomatik uyarı

**Alertler:**
1. **Service Down Alert**
   - Container stopped > 5 dakika
   - Health check failed > 3 kez

2. **High Memory Usage Alert**
   - Container memory > 90%
   - Host memory > 85%

3. **High CPU Usage Alert**
   - Container CPU > 80% (5 dakika)
   - Sustained high load

4. **Disk Space Alert**
   - Disk usage > 80%
   - Log disk > 70%

**Implementation:**
```yaml
# Prometheus alert rules
groups:
  - name: minder_alerts
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 5m
        annotations:
          summary: "Service {{ $labels.instance }} is down"
```

### 3.3 Güncelleme Dokümantasyonu
**Amaç:** Güncelleme süreçlerini dokümante et

**Dokümanlar:**
1. **Update Guide** (`docs/operations/UPDATE-GUIDE.md`)
2. **Troubleshooting Guide** (`docs/troubleshooting/UPDATES.md`)
3. **Rollback Procedures** (`docs/operations/ROLLBACK.md`)

**İçerik:**
- Güncelleme stratejileri
- Risk kategorileri
- Canary deployment prosedürü
- Emergency rollback adımları

---

## 📊 Mevcut Monitoring Altyapısı

### Prometheus
- URL: http://localhost:9090
- Status: ✅ Running
- Scrape interval: 15s
- Data retention: 15 days

### Grafana
- URL: http://localhost:3000
- Status: ✅ Running
- Default credentials: admin/admin
- Data source: Prometheus

### Telegraf
- Status: ✅ Running
- Input plugins: docker, cpu, mem, disk
- Output: InfluxDB

### InfluxDB
- URL: http://localhost:8086
- Status: ✅ Running
- Database: telegraf

---

## 🚀 Implementation Adımları

### Adım 1: Dashboard Oluşturma
```bash
# 1. Dashboard dizini oluştur
mkdir -p /root/minder/infrastructure/docker/grafana/dashboards

# 2. System Overview dashboard
cat > /root/minder/infrastructure/docker/grafana/dashboards/system-overview.json << 'DASHBOARD'
{
  "dashboard": {
    "title": "Minder System Overview",
    "panels": [
      {
        "title": "Container CPU Usage",
        "targets": [
          {
            "expr": "rate(container_cpu_usage_seconds_total{name!=\"\"}[5m])"
          }
        ]
      },
      {
        "title": "Container Memory Usage",
        "targets": [
          {
            "expr": "container_memory_usage_bytes"
          }
        ]
      }
    ]
  }
}
DASHBOARD

# 3. Dashboard'u Grafana'ya import et
curl -X POST http://localhost:3000/api/dashboards/import \
  -H "Content-Type: application/json" \
  -u admin:admin \
  -d @/root/minder/infrastructure/docker/grafana/dashboards/system-overview.json
```

### Adım 2: Alert Kuralları
```bash
# 1. Alert rules dizini oluştur
mkdir -p /root/minder/infrastructure/docker/prometheus/rules

# 2. Minder alert rules
cat > /root/minder/infrastructure/docker/prometheus/rules/minder-alerts.yml << 'RULES'
groups:
  - name: minder_system
    interval: 30s
    rules:
      - alert: ServiceDown
        expr: up == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Service {{ $labels.instance }} is down"
          description: "{{ $labels.job }} has been down for more than 5 minutes"

      - alert: HighMemoryUsage
        expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.name }}"
          description: "Container {{ $labels.name }} is using more than 90% memory"

      - alert: DiskSpaceHigh
        expr: (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.2
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Disk space running low"
          description: "Disk usage is above 80% on {{ $labels.instance }}"
RULES

# 3. Prometheus'ı restart et (alert rules'ı yüklemek için)
docker restart minder-prometheus
```

### Adım 3: Dokümantasyon
```bash
# 1. Dokümantasyon dizini oluştur
mkdir -p /root/minder/docs/operations
mkdir -p /root/minder/docs/troubleshooting

# 2. Update Guide oluştur
cat > /root/minder/docs/operations/UPDATE-GUIDE.md << 'GUIDE'
# Minder Platform Update Guide

## Güncelleme Stratejisi

### Risk Kategorileri
- **Düşük risk:** Monitoring, exporter'ler
- **Orta risk:** Vector DB, Graph DB  
- **Yüksek risk:** Core database, AI services

### Güncelleme Adımları
1. Backup al
2. Update check çalıştır
3. Canary test
4. Production update
5. Health check
6. Monitor et

### Rollback Prosedürü
1. Sorun tespiti
2. Servisi durdur
3. Eski image'i geri yükle
4. Verileri restore et
5. Doğrula
GUIDE

# 3. Troubleshooting Guide oluştur
cat > /root/minder/docs/troubleshooting/UPDATES.md << 'TROUBLE'
# Update Troubleshooting Guide

## Yaygın Sorunlar

### Sorun: Güncelleme sonrası servis başlamıyor
**Çözüm:** 
```bash
docker logs <service-name>
docker inspect <service-name>
./setup.sh doctor
```

### Sorun: Database migration hatası
**Çözüm:**
```bash
# Backup kontrol et
ls -lh /root/minder/backups/postgres/

# Migration loglarını kontrol et
docker logs minder-postgres | grep -i error

# Rollback
cat /root/minder/backups/postgres/manual-*/full-backup-*.sql | \
  docker exec -i minder-postgres psql -U minder
```

### Sorun: Rate limiting error
**Çözüm:**
```bash
# Cache temizle
rm -rf /root/minder/.cache/tags/*

# Tekrar dene
./setup.sh update --check
```
TROUBLE
```

---

## 📋 Yapılacaklar Listesi

### Bugün (Phase 3)
- [ ] System Overview Dashboard oluştur
- [ ] Service Health Dashboard oluştur  
- [ ] Alert kuralları konfigüre et
- [ ] Update Guide dokümantasyonu
- [ ] Troubleshooting Guide dokümantasyonu

### Bu Hafta
- [ ] Dashboard'ları test et
- [ ] Alert'leri doğrula
- [ ] Canary deployment prosedürü
- [ ] Rollback testi

### Bu Ay
- [ ] CI/CD entegrasyonu
- [ ] Automated monitoring
- [ ] Performance baseline
- [ ] Disaster recovery test

---

## ✅ Başarı Kriterleri

### Phase 3 (Bugün)
- ⏳ System Overview Dashboard aktif
- ⏳ Service Health Dashboard aktif
- ⏳ Alert kuralları konfigüre edildi
- ⏳ Dokümantasyon tamamlandı

---

**Rapor Durumu:** Phase 3 Başladı 🟡
**Tahmini Süre:** 2-3 saat
**Öncelik:** Monitoring ve dokümantasyon

