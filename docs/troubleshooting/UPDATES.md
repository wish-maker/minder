# Update Troubleshooting Guide

**Version:** 1.0.0  
**Last Updated:** 2026-05-10  
**Purpose:** Güncelleme sorunları için kapsamlı çözüm rehberi

---

## 🔧 Yaygın Update Sorunları

### Kategori 1: Update Check Sorunları

#### Sorun 1.1: Update Check Timeout
**Belirtiler:**
- `./setup.sh update --check` komutu 2+ dakika sürüyor
- Terminal donuyor, çıktı yok
- CTRL+C ile bile durdurulamıyor

**Nedenler:**
1. Docker Hub API rate limiting
2. Network connectivity issues
3. Cache corruption
4. Registry API changes

**Çözüm Adımları:**
```bash
# 1.1.1 Cache temizle
rm -rf /root/minder/.cache/tags/*
mkdir -p /root/minder/.cache/tags

# 1.1.2 Network kontrol et
ping -c 3 hub.docker.com
ping -c 3 ghcr.io
ping -c 3 quay.io

# 1.1.3 Docker Hub status kontrol et
curl -I https://hub.docker.com/v2/
# Expected: HTTP 200

# 1.1.4 Tekrar dene (verbose mode)
./setup.sh update --check 2>&1 | tee /tmp/update-check.log
```

**Alternatif Çözüm:**
```bash
# Rate limiting规避 için
SKIP_VERSION_CHECK=1 ./setup.sh update --check
```

---

#### Sorun 1.2: Cache Dosyası Bozuk
**Belirtiler:**
- Cache dosyası okunamıyor
- JSON parse error
- Garbage data in cache

**Çözüm:**
```bash
# 1.2.1 Cache dizini kontrol et
ls -la /root/minder/.cache/tags/

# 1.2.2 Bozuk cache dosyalarını temizle
find /root/minder/.cache/tags/ -name "*.json" -exec file {} \; | grep -v JSON
# Bozuk dosyaları sil
find /root/minder/.cache/tags/ -name "*.json" -exec rm {} \;

# 1.2.3 Cache'i yeniden oluştur
./setup.sh update --check
```

---

### Kategori 2: Image Pull Sorunları

#### Sorun 2.1: Image Bulunamıyor
**Belirtiler:**
- `manifest for <image>:<tag> not found`
- `unknown: manifest unknown`
- Image pull error

**Çözüm:**
```bash
# 2.1.1 Doğru tag'i kontrol et
curl -sf "https://hub.docker.com/v2/repositories/<image>/tags?page_size=10" | \
  grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]+"' | \
  sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//' | head -10

# 2.1.2 Alternatif tag kullan
docker pull <image>:latest
docker pull <image>:<major-version>

# 2.1.3 Image'ı manuel olarak etiketle
docker pull <image>:<correct-tag>
docker tag <image>:<correct-tag> <image>:<desired-tag>
```

**Örnek:**
```bash
# Grafana için
curl -sf "https://hub.docker.com/v2/repositories/grafana/grafana/tags?page_size=10" | \
  grep -o '"name"[[:space:]]*:[[:space:]]*"[^"]+"' | \
  sed 's/"name"[[:space:]]*:[[:space:]]*"//;s/"//' | head -10

# Çıktı: 11.6.0, 11.5.2, 11.4.0, ...
# Doğru tag'i seç: 11.6.0
docker pull grafana/grafana:11.6.0
```

---

#### Sorun 2.2: Network Timeout
**Belirtiler:**
- `context deadline exceeded`
- `net/http: timeout awaiting response`
- `connection timed out`

**Çözüm:**
```bash
# 2.2.1 Docker daemon restart
sudo systemctl restart docker

# 2.2.2 DNS kontrol et
docker run --rm alpine nslookup hub.docker.com

# 2.2.3 Proxy kontrol et (varsa)
echo $HTTP_PROXY
echo $HTTPS_PROXY

# 2.2.4 Alternative registry kullan
docker pull mirror.gcr.io/<image>:<tag>
```

---

### Kategori 3: Container Start Sorunları

#### Sorun 3.1: Container Başlamıyor
**Belirtiler:**
- Container status: `Exited (1)`
- `Restarting (1)` loop
- Health check failed

**Çözüm:**
```bash
# 3.1.1 Container loglarını kontrol et
docker logs --tail 100 <container-name>
docker logs --tail 500 <container-name> | grep -i error

# 3.1.2 Container inspection
docker inspect <container-name> | jq '.[0].State'

# 3.1.3 Config diff kontrol et
docker diff <container-name>

# 3.1.4 Manuel olarak başlat (debug)
docker run -it --rm <image>:<tag> /bin/sh
# Inside container: check startup scripts
```

**Yaygın Sebep ve Çözümler:**

**Sebep: Port Conflict**
```bash
# Port'u kontrol et
netstat -tulpn | grep <port>
lsof -i :<port>

# Çözüm: Port'u değiştir veya conflicting service'i durdur
```

**Sebep: Environment Variable Missing**
```bash
# .env dosyasını kontrol et
cat /root/minder/infrastructure/docker/.env | grep -i <service>

# Çözüm: Missing env var'ı ekle
echo "MISSING_VAR=value" >> /root/minder/infrastructure/docker/.env
```

**Sebep: Volume Mount Issue**
```bash
# Volume'u kontrol et
docker volume ls
docker volume inspect <volume-name>

# Çözüm: Volume'u oluştur veya permission'ları düzelt
mkdir -p /path/to/volume
chmod 755 /path/to/volume
```

---

#### Sorun 3.2: Health Check Failed
**Belirtiler:**
- Container running ama unhealthy
- Health check: `starting` → `unhealthy`
- Endpoint returns 404/500

**Çözüm:**
```bash
# 3.2.1 Health check endpoint'ini test et
docker exec <container-name> wget -O- http://localhost:<port>/health

# 3.2.2 Application loglarını kontrol et
docker logs <container-name> | grep -i "error\|exception\|panic"

# 3.2.3 Service dependencies kontrol et
docker exec <container-name> netstat -tulpn
# Port'lar açık mı?

# 3.2.4 Manual health check
docker exec <container-name> curl -f http://localhost:<port>/health || \
  echo "Health check failed"
```

**Özel Durumlar:**

**API Gateway:**
```bash
# PostgreSQL connection check
docker exec -it minder-api-gateway sh
ping -c 2 minder-postgres

# Environment variables check
docker exec minder-api-gateway env | grep -i database
```

**Database Services:**
```bash
# PostgreSQL connection test
docker exec -it minder-postgres psql -U minder -c "SELECT 1;"

# Redis connection test
docker exec -it minder-redis redis-cli PING
```

---

### Kategori 4: Database Migration Sorunları

#### Sorun 4.1: PostgreSQL Migration Failed
**Belirtiler:**
- Migration script failed
- Schema mismatch
- Constraint violation

**Çözüm:**
```bash
# 4.1.1 Mevcut schema'yı kontrol et
docker exec -it minder-postgres psql -U minder -d minder -c "\d"

# 4.1.2 Migration loglarını kontrol et
docker logs minder-postgres | grep -i migration

# 4.1.3 Manual migration çalıştır
docker exec -it minder-postgres psql -U minder -d minder -f /path/to/migration.sql

# 4.1.4 Data integrity check
docker exec -it minder-postgres psql -U minder -d minder -c "SELECT COUNT(*) FROM users;"
```

**Rollback Kararı:**
```bash
# Eğer migration başarısız olduysa:
# 1. Servisi durdur
docker stop minder-postgres

# 2. Backup'tan restore
cat /root/minder/backups/postgres/manual-*/full-backup-*.sql | \
  docker exec -i minder-postgres psql -U minder

# 3. Verify data
docker exec -it minder-postgres psql -U minder -d minder -c "SELECT COUNT(*) FROM users;"
```

---

#### Sorun 4.2: Neo4j Upgrade Failed
**Belirtiler:**
- Store migration failed
- Data inconsistency
- Rollback needed

**Çözüm:**
```bash
# 4.2.1 Neo4j loglarını kontrol et
docker logs minder-neo4j | grep -i "error\|migration"

# 4.2.2 Database status check
docker exec -it minder-neo4j cypher-shell -u neo4j -p <password>
SHOW DATABASES;

# 4.2.3 Data consistency check
docker exec -it minder-neo4j cypher-shell -u neo4j -p <password>
MATCH (n) RETURN count(n);

# 4.2.4 Backup'tan restore (gerektiğinde)
docker stop minder-neo4j
docker cp /root/minder/backups/neo4j/manual-*/data/. \
  minder-neo4j:/data/
docker start minder-neo4j
```

---

### Kategori 5: Post-Update Sorunları

#### Sorun 5.1: Performance Degradation
**Belirtiler:**
- Response time arttı
- CPU/Memory usage yüksek
- Latency spike

**Çözüm:**
```bash
# 5.1.1 Metrics kontrol et
curl http://localhost:9090/api/v1/query?query=rate(http_request_duration_seconds_sum[5m])

# 5.1.2 Container resource usage
docker stats minder-<service-name> --no-stream

# 5.1.3 Application profiling
docker exec minder-<service-name> py-spy top --pid 1

# 5.1.4 Compare with baseline
# Update öncesi ve sonrası metrics comparison
```

**Mitigation:**
```bash
# Resource limit'ları artır
# docker-compose.yml'de:
services:
  <service>:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

# Restart service
docker-compose up -d <service>
```

---

#### Sorun 5.2: API Breaking Changes
**Belirtiler:**
- 404 Not Found on endpoints
- Schema validation errors
- Client compatibility issues

**Çözüm:**
```bash
# 5.2.1 API documentation check
curl -f http://localhost:8000/docs
curl -f http://localhost:8000/openapi.json

# 5.2.2 Client compatibility test
# API endpoint test
curl -X POST http://localhost:8000/api/v1/plugins \
  -H "Content-Type: application/json" \
  -d '{"name":"test"}'

# 5.2.3 Version negotiation
curl -H "Accept: application/vnd.minder.v1+json" \
  http://localhost:8000/api/v1/plugins
```

---

## 🚨 Emergency Procedures

### Emergency Rollback
```bash
# 1. Tüm servisleri durdur (kritik durumda)
./setup.sh stop

# 2. En son backup'tan restore
LATEST_BACKUP=$(ls -t /root/minder/backups/ | head -1)
./setup.sh restore /root/minder/backups/$LATEST_BACKUP/

# 3. Servisleri başlat
./setup.sh start

# 4. Health check
./setup.sh status
```

### Graceful Degradation
```bash
# 1. Etkilen servisi durdur
docker stop minder-<problematic-service>

# 2. Alternative route aktif et (traefik)
# Traefik dashboard: http://localhost:8081

# 3. Monitor system load
docker stats --no-stream

# 4. İncident log
echo "$(date): Service <problematic-service> stopped due to <issue>" >> \
  /root/minder/incident.log
```

---

## 📞 Destek ve Escalation

### Self-Service Checklist
- [ ] Logları kontrol et (docker logs)
- [ ] Documentation oku (UPDATE-GUIDE.md)
- [ ] Common solutions dene (bu guide)
- [ ] Backup verify et
- [ ] Rollback değerlendir

### Destek Kanalları
1. **Internal Documentation:** `/root/minder/docs/`
2. **Setup.sh Doctor:** `./setup.sh doctor`
3. **Community Forums:** (link varsa)
4. **Emergency Contact:** (bilgi varsa)

---

**Not:** Bu troubleshooting guide güncelleme sırasında karşılaşılan yaygın sorunlar için çözüm yolları içerir. Her sorunda önce backup durumunu kontrol edin.

