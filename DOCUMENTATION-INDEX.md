# 📚 Minder Platform - Dokümantasyon İndeksi

Bu dosya tüm dokümantasyonun hızlı erişim indeksidir.

## 🎯 Hızlı Bulma

### Aradığınız şeyi buradan bulun:

- **"Sistemi nasıl kurarım?"** → [Kurulum Rehberi](docs/getting-started/installation.md)
- **"Platform nasıl çalışır?"** → [Mimari Genel Bakış](docs/architecture/overview.md)
- **"Plugin nasıl yazarım?"** → [Plugin Geliştirme](docs/development/plugin-development.md)
- **"Sistem çalışmıyor, ne yapmalıyım?"** → [Sorun Giderme](docs/troubleshooting/common-issues.md)
- **"Production'a nasıl alırım?"** → [Production Deployment](docs/deployment/production.md)
- **"Şu anki durum nedir?"** → [Günlük Durum Raporu](docs/operations/reports/PROJE-DURUMU-2026-05-06.md)

---

## 📖 Kategorilere Göre Dokümantasyon

### 🚀 Başlarken
1. [Kurulum Rehberi](docs/getting-started/installation.md) - Detaylı kurulum adımları
2. [Hızlı Başlangıç](docs/getting-started/quick-start.md) - 5 dakikada başlayın
3. [AI Kurulumu](docs/getting-started/ai-setup.md) - AI hizmetleri yapılandırması
4. [Platform Genel Bakış](docs/architecture/overview.md) - Sistem mimarisi

### 🏗️ Mimari & Tasarım
1. [Mikroservis Mimarisi](docs/architecture/microservices.md) - 25 hizmetin yapısı
2. [Plugin Sistemi](docs/architecture/plugins.md) - Plugin mimarisi
3. [Proje Yapısı](docs/architecture/project-structure.md) - Kod organizasyonu
4. [Yol Haritası](docs/architecture/roadmap.md) - Gelecek planlar

### 💻 Geliştirme
1. [Geliştirme Ortamı](docs/development/development.md) - Local setup
2. [Plugin Geliştirme](docs/development/plugin-development.md) - Plugin yazma
3. [Test Stratejileri](docs/development/testing.md) - Test yazma
4. [Kod Stili](docs/development/code-style.md) - Kodlama standartları

### 🚀 Deployment
1. [Production Deployment](docs/deployment/production.md) - Canlıya alma
2. [Donanım Optimizasyonu](docs/deployment/hardware-optimization.md) - Performans
3. [Monitoring Kurulumu](docs/deployment/monitoring.md) - İzleme sistemi
4. [Docker Deployment](infrastructure/docker/README.md) - Docker Compose

### 🔧 Operasyonlar
1. [Operasyonel Kılavuz](docs/operations/README.md) - Günlük operasyonlar
2. [Sistem Durum Raporu](docs/operations/reports/PROJE-DURUMU-2026-05-06.md) - Son durum
3. [API Test Sonuçları](docs/operations/reports/API-ENDPOINTS-TEST-RESULTS.md) - Endpoint testleri
4. [Docker Yönetimi](infrastructure/docker/README.md) - Container yönetimi

### 🔒 Güvenlik
1. [Kimlik Doğrulama](docs/guides/authentication.md) - Authelia SSO
2. [Güvenlik Kurulumu](docs/guides/security-setup.md) - Güvenlik best practices

### 🐛 Sorun Giderme
1. [Sık Sorunlar](docs/troubleshooting/common-issues.md) - Yaygın sorunlar ve çözümler
2. [Acil Prosedürler](docs/troubleshooting/emergency-procedures.md) - Kriz yönetimi
3. [Docker Sorunları](infrastructure/docker/README.md#sorun-giderme) - Container sorunları

### 🔌 API
1. [API Referansı](docs/api/reference.md) - Tüm endpoint'ler
2. [API Kılavuzu](docs/api/README.md) - API kullanımı

### 📔 Arşiv
1. [Eski Raporlar](docs/archive/reports/) - Geçmiş dönem raporları
2. [Oturum Özetleri](docs/archive/sessions/) - Çalışma oturumları

---

## 🗂️ Dosya Yapısı

```
minder/
├── README.md                          # Ana proje README
├── CONTRIBUTING.md                    # Katkı rehberi
├── DOCUMENTATION-INDEX.md             # Bu dosya
│
├── docs/                              # Ana dokümantasyon
│   ├── README.md                      # Dokümantasyon ana sayfa
│   │
│   ├── getting-started/              # Başlarken
│   │   ├── installation.md
│   │   ├── quick-start.md
│   │   └── ai-setup.md
│   │
│   ├── architecture/                 # Mimari
│   │   ├── overview.md
│   │   ├── microservices.md
│   │   ├── plugins.md
│   │   ├── project-structure.md
│   │   └── roadmap.md
│   │
│   ├── development/                  # Geliştirme
│   │   ├── development.md
│   │   ├── plugin-development.md
│   │   ├── testing.md
│   │   └── code-style.md
│   │
│   ├── deployment/                   # Deployment
│   │   ├── production.md
│   │   ├── hardware-optimization.md
│   │   └── monitoring.md
│   │
│   ├── operations/                   # Operasyonlar
│   │   ├── README.md
│   │   └── reports/
│   │       ├── PROJE-DURUMU-2026-05-06.md
│   │       └── API-ENDPOINTS-TEST-RESULTS.md
│   │
│   ├── guides/                       # Rehberler
│   │   ├── authentication.md
│   │   └── security-setup.md
│   │
│   ├── troubleshooting/              # Sorun giderme
│   │   ├── common-issues.md
│   │   └── emergency-procedures.md
│   │
│   ├── api/                          # API dokümantasyonu
│   │   ├── README.md
│   │   └── reference.md
│   │
│   └── archive/                      # Arşiv
│       ├── reports/                  # Eski raporlar
│       └── sessions/                 # Oturum özetleri
│
├── infrastructure/                   # Altyapı
│   ├── docker/                       # Docker yapılandırması
│   │   ├── docker-compose.yml
│   │   ├── README.md
│   │   ├── .env.example
│   │   ├── prometheus/              # Prometheus config
│   │   ├── grafana/                 # Grafana dashboards
│   │   └── authelia/                # Authelia config
│   │
│   └── schema-registry/             # Schema registry
│
├── services/                         # Mikroservis kodları
│   ├── api-gateway/
│   ├── plugin-registry/
│   ├── rag-pipeline/
│   └── ...
│
└── backups/                          # Yedekler
    ├── backup-databases.sh          # Yedek scripti
    ├── postgres/                    # PostgreSQL yedekleri
    ├── redis/                       # Redis yedekleri
    └── neo4j/                       # Neo4j yedekleri
```

---

## 🎯 Kullanım Senaryoları

### Senaryo 1: Yeni Geliştirici
**"Projeye yeni başladım, nereden başlamalıyım?"**

1. Oku: [Hızlı Başlangıç](docs/getting-started/quick-start.md)
2. Kur: [Kurulum Rehberi](docs/getting-started/installation.md)
3. Öğren: [Mimari Genel Bakış](docs/architecture/overview.md)
4. Geliştir: [Geliştirme Ortamı](docs/development/development.md)

### Senaryo 2: Plugin Geliştirici
**"Plugin yazmak istiyorum, nasıl yaparım?"**

1. Oku: [Plugin Sistemi](docs/architecture/plugins.md)
2. Öğren: [Plugin Geliştirme](docs/development/plugin-development.md)
3. Örnek: [Plugin Examples](examples/)
4. Test: [Test Stratejileri](docs/development/testing.md)

### Senaryo 3: DevOps Mühendisi
**"Sistemi production'a alacağım"**

1. Oku: [Production Deployment](docs/deployment/production.md)
2. Planla: [Monitoring Kurulumu](docs/deployment/monitoring.md)
3. Hazırla: [Yedekleme Stratejisi](infrastructure/docker/README.md#yedekleme)
4. Test: [Acil Prosedürler](docs/troubleshooting/emergency-procedures.md)

### Senaryo 4: Sistem Yöneticisi
**"Sistemde sorun var, ne yapmalıyım?"**

1. Kontrol: [Sistem Durumu](docs/operations/reports/PROJE-DURUMU-2026-05-06.md)
2. Teşhis: [Sık Sorunlar](docs/troubleshooting/common-issues.md)
3. Çöz: [Docker Sorunları](infrastructure/docker/README.md#sorun-giderme)
4. Destek: [Acil Prosedürler](docs/troubleshooting/emergency-procedures.md)

---

## 📊 Dokümantasyon Durumu

### ✅ Tamamlanmış
- ✅ Kurulum rehberleri
- ✅ Mimari dokümantasyonu
- ✅ API referansı
- ✅ Docker deployment
- ✅ Sorun giderme kılavuzları
- ✅ Operasyonel rehberler

### 🚧 Devam Ediyor
- 🚧 Plugin development tutorials
- 🚧 Advanced monitoring guides
- 🚧 Performance tuning guides
- 🚧 Multi-region deployment

### 📋 Planlanıyor
- 📋 Video tutorials
- 📋 Interactive examples
- 📋 Architecture decision records
- 📋 Migration guides

---

## 🔍 Arama İpuçları

### Dokümanlarda Arama Yapma

```bash
# Ana dizinde arama
grep -r "keyword" docs/

# Belirli bir klasörde arama
grep -r "keyword" docs/troubleshooting/

# Dosya adında arama
find docs/ -name "*keyword*"
```

### Doküman Güncellemeleri

Her dokümanın sonunda "Son Güncelleme" tarihi vardır.
En güncel bilgiler için tarihleri kontrol edin.

---

## 💡 Katkı Sağlama

Dokümantasyonu iyileştirmek için:
1. Eksik bilgiyi tamamlayın
2. Örnek ekleyin
3. Hataları düzeltin
4. [CONTRIBUTING.md](CONTRIBUTING.md) rehberini takip edin

---

## 📞 Destek

Dokümantasyonla ilgili sorularınız için:
- 📖 [Dokümantasyon README](docs/README.md)
- 🐛 [Bug Report](https://github.com/your-repo/minder/issues)
- 💬 [Discussions](https://github.com/your-repo/minder/discussions)

---

**Son Güncelleme:** 2026-05-06  
**Dokümantasyon Sürümü:** 1.0  
**Toplam Doküman:** 50+ dosya
