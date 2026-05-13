# Minder Platform - Docker Deployment

Bu dizin Minder platformunun Docker Compose ile deployment yapılandırmasını içerir.

## 🐳 Hizmetler (25 Konteyner)

### Çekirdek Altyapı
- **Traefik** - Reverse proxy ve load balancer (Port: 80, 443, 8081)
- **Authelia** - SSO kimlik doğrulama (Port: 9091)
- **API Gateway** - Merkezi API gateway (Port: 8000)

### Veritabanları
- **PostgreSQL** - İlişkisel veritabanı (Dahili ağ)
- **Redis** - Cache ve message broker (Dahili ağ)
- **Neo4j** - Graf veritabanı (Dahili ağ)
- **InfluxDB** - Zaman serisi veritabanı (Dahili ağ)
- **Qdrant** - Vektör veritabanı (Dahili ağ)

### AI Hizmetleri
- **Ollama** - LLM inference motoru (Port: 11434)
- **OpenWebUI** - AI chat arayüzü (Port: 8080)
- **RAG Pipeline** - Retrieval Augmented Generation (Dahili ağ)
- **Model Management** - Model yönetimi (Dahili ağ)
- **TTS-STT Service** - Ses/speech-to-text (Port: 8006)
- **Model Fine-tuning** - Model fine-tuning (Port: 8007)

### Mesajlaşma
- **RabbitMQ** - Message broker (Port: 15672)

### Gözlemlenebilirlik
- **Prometheus** - Metrik toplama (Port: 9090)
- **Grafana** - Görselleştirme (Port: 3000)
- **Alertmanager** - Alert yönetimi (Port: 9093)
- **Telegraf** - Metrik toplama aracısı (Dahili ağ)

### Exporters
- **PostgreSQL Exporter** - DB metrikleri (Port: 9187)
- **Redis Exporter** - Cache metrikleri (Port: 9121)
- **RabbitMQ Exporter** - MQ metrikleri (Port: 9419)

### Uygulama Hizmetleri
- **Plugin Registry** - Plugin kayıt (Dahili ağ)
- **Plugin State Manager** - Plugin durum (Dahili ağ)
- **Marketplace** - Plugin marketplace (Dahili ağ)

---

## 🚀 Hızlı Başlangıç

### Sistemi Başlatma

```bash
# Tüm hizmetleri başlat
docker compose up -d

# Servis durumunu kontrol et
docker ps

# Logları görüntüle
docker compose logs -f
```

### Sistemi Durdurma

```bash
# Tüm hizmetleri durdur
docker compose down

# Volumeleri koruyarak durdur
docker compose down --remove-orphans
```

### Yeniden Başlatma

```bash
# Tüm hizmetleri yeniden başlat
docker compose restart

# Belirli bir hizmeti yeniden başlat
docker compose restart <service-name>
```

---

## 🔧 Yapılandırma

### Ortam Değişkenleri

```bash
# .env dosyasını kopyala ve düzenle
cp .env.example .env

# Güçlü şifreler oluştur
openssl rand -base64 32  # AUTHELIA_SECRET için
```

### Gerekli Ortam Değişkenleri

```bash
# Veritabanı şifreleri
POSTGRES_PASSWORD=güçlü_şifre
REDIS_PASSWORD=güçlü_şifre

# Authelia secrets
AUTHELIA_STORAGE_ENCRYPTION_KEY=güçlü_secret
AUTHELIA_JWT_SECRET=güçlü_secret
AUTHELIA_SESSION_SECRET=güçlü_secret

# Neo4j
NEO4J_AUTH=neo4j/güçlü_şifre
```

---

## 📊 Monitoring

### Prometheus
- **URL:** http://localhost:9090
- **Ne izler:** Tüm 25 hizmet
- **Scrape aralığı:** 15 saniye

### Grafana
- **URL:** http://localhost:3000
- **Varsayılan:** admin/admin (DEĞİŞTİRİN!)
- **Dashboard'lar:** Sistem genel bakış, servis metrikleri

### Alertmanager
- **URL:** http://localhost:9093
- **Alert grupları:** 9
- **Kurallar:** 45+

---

## 🗄️ Yedekleme

### Otomatik Yedekler
- **Sıklık:** Her gün 02:00'de
- **Saklama:** 7 gün
- **Konum:** `/root/minder/backups/`

### Manuel Yedekleme
```bash
# Tüm veritabanlarını yedekle
/root/minder/backups/backup-databases.sh full

# Sadece PostgreSQL'i yedekle
/root/minder/backups/backup-databases.sh postgres

# Yedek istatistiklerini görüntüle
/root/minder/backups/backup-databases.sh stats
```

---

## 🔐 Güvenlik

### Zero-Trust Mimarisi
- ✅ Traefik reverse proxy
- ✅ Authelia SSO kimlik doğrulama
- ✅ Dahili ağ izolasyonu
- ✅ SSL/TLS şifreleme

### Erişim Kontrolü
- **Public erişim:** public.minder.local
- **Auth gerektirir:** *.minder.local
- **2FA gerektirir:** admin.minder.local, api.minder.local

---

## 🐛 Sorun Giderme

### Konteyner Başlamıyor
```bash
# Logları kontrol et
docker logs <container-name>

# Yapılandırmayı doğrula
docker compose config

# Volumeleri kontrol et
docker volume ls
```

### Servis Erişilemez
```bash
# Ağ durumunu kontrol et
docker network ls
docker network inspect minder-network

# Servis sağlık kontrolü
curl http://localhost:8000/health
```

### Yüksek Kaynak Kullanımı
```bash
# Kaynak kullanımını görüntüle
docker stats

# Konteyner limitlerini kontrol et
docker inspect <container-name> | grep -A 10 "HostConfig"
```

---

## 📈 Performans Optimizasyonu

### Kaynak Limitleri
Tüm konteynerler için CPU ve bellek limitleri tanımlanmıştır.
Düzenleme için `docker-compose.yml` içindeki `deploy.resources` bölümünü düzenleyin.

### Scaling
```bash
# Bir servisi scale et
docker compose up -d --scale <service-name>=<replicas>

# Örnek: API Gateway'i 3 replica'ya çıkar
docker compose up -d --scale api-gateway=3
```

---

## 🔄 Upgrade

### Güvenli Upgrade Prosedürü
1. Yedek alın: `/root/minder/backups/backup-databases.sh full`
2. Sistemi durdurun: `docker compose down`
3. Image'ları çekin: `docker compose pull`
4. Sistemi başlatın: `docker compose up -d`
5. Durumu kontrol edin: `docker ps`

Detaylı bilgi için: [UPGRADE-RUNBOOK.md](UPGRADE-RUNBOOK.md)

---

## 📚 Ek Dokümantasyon

- [Genel Dokümantasyon](../../docs/README.md)
- [Sorun Giderme](../../docs/troubleshooting/common-issues.md)
- [Production Deployment](../../docs/deployment/production.md)
- [API Reference](../../docs/api/reference.md)

---

## 🆘 Destek

Sorun yaşarsanız:
1. [Sorun Giderme Kılavuzu](../../docs/troubleshooting/common-issues.md)
2. [GitHub Issues](https://github.com/your-repo/issues)
3. [Acil Prosedürler](../../docs/troubleshooting/emergency-procedures.md)

---

**Son Güncelleme:** 2026-05-06  
**Sürüm:** 1.0.0  
**Durum:** 🟢 Production Ready
