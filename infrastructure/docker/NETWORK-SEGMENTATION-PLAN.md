# Network Segmentation Plan for Minder Platform

**Tarih:** 2026-05-07
**Durum:** 🟡 PLANLAMA AŞAMASI
**Öncelik:** Orta (Güvenlik İyileştirmesi)

## 📊 Mevcut Durum Analizi

### Mevcut Network Yapısı
- **Tek Network:** `minder-network` (29 servis)
- **Tüm Servisler:** Aynı bridge network üzerinde
- **Risk:** Servisler arası izolasyon yok, lateral movement riski var

### Mevcut Servis Dağılımı
**Kritik Servisler (29/31):**
- Authelia, API Gateway, Plugin Registry
- PostgreSQL, Redis, Neo4j
- RAG Pipeline, Model Management
- OpenWebUI, Marketplace
- Prometheus, Grafana, Telegraf
- RabbitMQ, Qdrant
- Diğer microservisler

**Diğer Servisler (2/31):**
- Traefik (separate network - management)

## 🎯 Network Segmentation Stratejisi

### Seviye 1: Security Zones (Güvenlik Bölgeleri)

#### Zone 1: Public Internet Facing (DMZ)
**Servisler:**
- Traefik (Reverse Proxy)
- Authelia (Authentication)

**Network:** `minder-public`
**Açıklama:** İnternete açık olan servisler
**Risk:** Yüksek (saldırı yüzeyi)
**Erişim:** Sadece Zone 2'ye

#### Zone 2: Application Services
**Servisler:**
- API Gateway
- Plugin Registry
- Marketplace
- RAG Pipeline
- Model Management
- Model Fine-tuning
- Plugin State Manager
- OpenWebUI
- TTS-STT Service

**Network:** `minder-apps`
**Açıklama:** Uygulama katmanı servisleri
**Risk:** Orta
**Erişim:** Zone 1'den, Zone 3'e

#### Zone 3: Data Services
**Servisler:**
- PostgreSQL
- Redis
- Neo4j
- Qdrant
- RabbitMQ

**Network:** `minder-data`
**Açıklama:** Veritabanı ve message broker
**Risk:** Kritik (en hassas veriler)
**Erişim:** Sadece Zone 2'den

#### Zone 4: Monitoring & Management
**Servisler:**
- Prometheus
- Grafana
- Telegraf
- Alertmanager
- cAdvisor
- Node Exporter
- PostgreSQL Exporter
- Redis Exporter
- RabbitMQ Exporter

**Network:** `minder-monitoring`
**Açıklama:** Monitoring ve observability servisleri
**Risk:** Düşük
**Erişim:** Tüm zone'lardan (read-only)

### Seviye 2: Network Isolation Kuralları

#### Zone 1 → Zone 2 (Public → Apps)
**İzin Verilen:**
- HTTP/HTTPS traffic (80, 443)
- WebSocket connections

**Engellenen:**
- Doğrudan veritabanı erişimi
- Servis discovery (internal DNS)

#### Zone 2 → Zone 3 (Apps → Data)
**İzin Verilen:**
- PostgreSQL (5432)
- Redis (6379)
- Neo4j (7474, 7687)
- Qdrant (6333)
- RabbitMQ (5672, 15672)

**Engellenen:**
- P2P servis ile servis iletişim
- Zone 1'den doğrudan erişim

#### Zone 2 → Zone 4 (Apps → Monitoring)
**İzin Verilen:**
- Prometheus (9090)
- Grafana (3000)

**Engellenen:**
- Monitoring servislerinin apps servislerine başlatması

### Seviye 3: Firewall Kuralları

#### Docker Compose Network Yapılandırması
```yaml
networks:
  minder-public:
    driver: bridge
    internal: false
    ipam:
      config:
        - subnet: 172.20.0.0/24

  minder-apps:
    driver: bridge
    internal: true
    ipam:
      config:
        - subnet: 172.21.0.0/24

  minder-data:
    driver: bridge
    internal: true
    ipam:
      config:
        - subnet: 172.22.0.0/24

  minder-monitoring:
    driver: bridge
    internal: true
    ipam:
      config:
        - subnet: 172.23.0.0/24
```

## 🚀 Uygulama Adımları

### Adım 1: Network Oluşturma
```bash
# Mevcut network'ı koru (geçiş dönemi)
docker network create minder-public --subnet 172.20.0.0/24
docker network create minder-apps --internal --subnet 172.21.0.0/24
docker network create minder-data --internal --subnet 172.22.0.0/24
docker network create minder-monitoring --internal --subnet 172.23.0.0/24
```

### Adım 2: Servis Migration Planı

#### Faz 1: Monitoring Servisleri (Risk-free)
1. Prometheus → minder-monitoring
2. Grafana → minder-monitoring
3. Telegraf → minder-monitoring
4. Exporters → minder-monitoring

**Test:** Monitoring çalışıyor mu?
**Rollback:** Kolay (geri minder-network)

#### Faz 2: Data Servisleri (Kritik)
1. PostgreSQL → minder-data
2. Redis → minder-data
3. Neo4j → minder-data
4. Qdrant → minder-data
5. RabbitMQ → minder-data

**Test:** Uygulamalar veritabanlarına erişebiliyor mu?
**Rollback:** Orta (connection string'ler geri)

#### Faz 3: Application Servisleri (En kritik)
1. API Gateway → minder-apps + minder-public
2. Plugin Registry → minder-apps
3. Marketplace → minder-apps
4. OpenWebUI → minder-apps
5. Diğer microservisler → minder-apps

**Test:** Tüm API endpoint'leri çalışıyor mu?
**Rollback:** Zor (tüm servisler)

### Adım 3: Traefik Configuration Güncelleme
```yaml
# Zone 1 (Public)
traefik:
  networks:
    - minder-public
    - minder-apps

# Zone 2 (Apps)
api-gateway:
  networks:
    - minder-apps

# Zone 3 (Data)
postgres:
  networks:
    - minder-data

# Zone 4 (Monitoring)
prometheus:
  networks:
    - minder-monitoring
    - minder-apps  # Scrape apps için
```

## 📋 Risk Analizi

### Yüksek Risk Alanları
1. **Connection String Değişiklikleri** - Tüm servisler güncellenmeli
2. **Service Discovery** - Docker DNS update gerekli
3. **Downtime Riski** - Migration sırasında kesinti olabilir

### Azaltma Stratejileri
1. **Blue-Green Deployment** - Yeni network'lar paralel çalışır
2. **Phase Migration** - Servisleri gruplar halinde taşı
3. **Comprehensive Testing** - Her faz sonrası test
4. **Rollback Planı** - Her faz için geri dönüş planı

## 🔒 Güvenlik İyileştirmeleri

### Kazanımlar
1. **Lateral Movement Önleme** - Zone'lar arası izolasyon
2. **Data Protection** - Veritabanları doğrudan erişilemez
3. **Attack Surface Reduction** - Public facing servisler azaltıldı
4. **Compliance** - Security best practices uyumu

### Ek Güvenlik Önlemleri
1. **Network Policies** - Docker network policies
2. **Service Mesh** - Istio/Linkerd (gelecek)
3. **Zero Trust** - mTLS between services (gelecek)
4. **Secrets Management** - HashiCorp Vault (gelecek)

## 📊 Etki Analizi

### Performans Etkisi
- **Network Latency:** +1-2ms (ekstra network hop)
- **Throughput:** Etkilenmez (%0 change)
- **Security:** %90+ iyileştirme

### Bakım Maliyeti
- **Complexity:** Artıyor (4 network vs 1)
- **Troubleshooting:** Biraz daha zor
- **Documentation:** Kapsamlı dokümante gerekli

## ⏭️ Uygulama Zaman Çizelgesi

### Hafta 1: Planlama ve Test
- [ ] Network tasarımını finalizes et
- [ ] Test ortamında oluştur
- [ ] Migration script'lerini yaz

### Hafta 2: Monitoring Migration
- [ ] Monitoring network'ı oluştur
- [ ] Monitoring servislerini taşı
- [ ] Test ve validates et

### Hafta 3: Data Services Migration
- [ ] Data network'ı oluştur
- [ ] Veritabanlarını taşı
- [ ] Uygulama bağlantılarını test et

### Hafta 4: Application Migration
- [ ] Apps network'ı oluştur
- [ ] Uygulama servislerini taşı
- [ ] Tüm sistemi test et
- [ ] Eski network'ı kaldır

### Hafta 5: Optimization
- [ ] Network policies ekle
- [ ] Performance test et
- [ ] Documentation oluştur

## 🎯 Başarı Metrikleri

### Kısa Vadeli (1 Ay)
- ✅ 4 zone oluşturuldu
- ✅ Tüm servisler migrate edildi
- ✅ %100 uptime (no downtime)
- ✅ Security score %90 iyileştirme

### Uzun Vadeli (3 Ay)
- ✅ Zero Trust mTLS implementasyonu
- ✅ Service mesh entegrasyonu
- ✅ Automated network policies
- ✅ %99.9 compliance score

## 💡 Alternatif Yaklaşımlar

### Seçenek 1: Kubernetes Network Policies
**Artıları:**
- Native network segmentation
- Declarative configuration
- Ecosystem tool support

**Eksileri:**
- K8s gerektirir
- Daha yüksek complexity

### Seçenek 2: Service Mesh (Istio/Linkerd)
**Artıları:**
- Advanced traffic management
- mTLS by default
- Observability built-in

**Eksileri:**
- Yüksek resource overhead
- Complex setup

### Seçenek 3: Mevcut Yaklaşım (Docker Networks)
**Artıları:**
- Basit implementation
- Low overhead
- Docker native

**Eksileri:**
- Manual configuration
- Limited features

## 🏆 Sonuç ve Öneri

**Öneri:** Mevcut Docker Compose ortamı için **Seçenek 3 (Docker Networks)** en uygun.

**Nedenleri:**
1. Mevcut infrastructure Docker Compose
2. K8s migration planı yok
3. Service mesh overhead'i kabul edilemez değil
4. Basit ve effectif çözüm gerekiyor

**Sonraki Adım:** Test ortamında pilot implementation başlat.

---

**Durum:** Plan hazır, implementation için onay bekliyor.
**Öncelik:** Orta (Security improvement, blocking issue değil)
**Zaman Çerçevesi:** 4-5 hafta
**Risk:** Yönetilebilir (phase migration ile)
