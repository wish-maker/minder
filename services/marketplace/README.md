# 🛒 Minder Plugin Marketplace

Modern, scalable plugin marketplace ve lisans yönetim sistemi için FastAPI tabanlı mikroservis.

## 🚀 Hızlı Başlangıç

### Prerequisites
- Docker ve Docker Compose
- Python 3.11+ (local development için)
- PostgreSQL 16+ (veya Docker ile)
- Redis 7+ (veya Docker ile)

### Hızlı Başlatma (Docker)

```bash
# 1. Tüm servisleri başlat
cd /root/minder/infrastructure/docker
docker compose -f docker-compose.yml -f docker-compose.marketplace.yml up -d

# 2. Servislerin durumunu kontrol et
docker ps --filter "name=minder-"

# 3. Health check
curl http://localhost:8002/health
```

### Local Development

```bash
# 1. Virtual environment oluştur
cd /root/minder
python -m venv venv
source venv/bin/activate

# 2. Dependencies yükle
pip install -r services/marketplace/requirements.txt

# 3. Environment variables ayarla
cp services/marketplace/.env.example services/marketplace/.env
# Edit services/marketplace/.env with your settings

# 4. Database migrasyonlarını çalıştır
docker exec minder-postgres psql -U minder -d minder_marketplace -f /app/services/marketplace/migrations/001_initial_schema.sql

# 5. Servisi başlat
cd services/marketplace
uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

## 📚 API Dokümantasyonu

Swagger UI dokümantasyonu servis başladığında otomatik olarak yüklenir:

- **Production**: `http://your-domain:8002/docs`
- **Development**: `http://localhost:8002/docs`
- **ReDoc**: `http://localhost:8002/redoc`

## 🔌 Temel Endpoint'ler

### Plugin Keşfi
```bash
# Tüm pluginleri listele (sayfalama)
GET /v1/marketplace/plugins?page=1&page_size=10

# Plugin ara
GET /v1/marketplace/plugins/search?q=chat+assistant

# Öne çıkan pluginler
GET /v1/marketplace/plugins/featured

# Plugin detayları
GET /v1/marketplace/plugins/{plugin_id}
```

### Lisans Yönetimi
```bash
# Lisans aktifleştir
POST /v1/marketplace/licenses/activate
{
  "user_id": "uuid",
  "plugin_id": "uuid",
  "tier": "community|basic|pro|enterprise"
}

# Lisans doğrula
POST /v1/marketplace/licenses/validate
{
  "license_key": "XXXX-XXXX-XXXX-XXXX",
  "plugin_id": "uuid"
}

# Kullanıcı lisanslarını listele
GET /v1/marketplace/licenses?user_id=uuid
```

### AI Araçları
```bash
# Tüm AI araçlarını listele
GET /v1/marketplace/ai/tools

# Plugin'e göre AI araçları
GET /v1/marketplace/ai/plugins/{plugin_id}/tools

# AI araç detayları
GET /v1/marketplace/ai/tools/{tool_name}
```

## 🗄️ Database Schema

### Ana Tablolar

#### `marketplace_plugins`
Plugin bilgilerini tutar:
- Temel bilgiler (isim, açıklama, yazar)
- Sınıflandırma (kategori, fiyatlandırma modeli)
- Sürüm ve dağıtım bilgileri
- İstatistikler (indirme sayısı, puan)

#### `marketplace_users`
Marketplace kullanıcıları:
- Profil bilgileri
- API anahtarları
- Tercihler ve ayarlar

#### `marketplace_licenses`
Lisans anahtarları ve haklar:
- HMAC-tabanlı lisans anahtarları
- Kullanıcı-plugin-tier ilişkileri
- Geçerlilik tarihleri

#### `marketplace_installations`
Plugin kurulum takibi:
- Kullanıcı başına kurulum bilgileri
- Durum takibi (aktif/pasif/devre dışı)

#### `marketplace_ai_tools`
AI araçları kaydı:
- Tool metadata
- Tier ve erişim kontrolü
- Rate limiting bilgileri

### Tam Schema Detayları
`docs/DATABASE_SCHEMA.md` dosyasına bakın.

## 🔐 Güvenlik

### Lisans Anahtarı Üretimi
- HMAC-SHA256 tabanlı
- User ID + Plugin ID + Timestamp birleşimi
- 4 gruplu format: `XXXX-XXXX-XXXX-XXXX`

### Veri Doğrulama
- UUID format kontrolü (Pydantic)
- Foreign key constraints (PostgreSQL)
- Input sanitization (HTML escaping for user content)
- Rate limiting (Redis tabanlı)

### Environment Variables
```bash
# Database
MARKETPLACE_DATABASE_HOST=postgres
MARKETPLACE_DATABASE_PORT=5432
MARKETPLACE_DATABASE_USER=minder
MARKETPLACE_DATABASE_PASSWORD=your_password
MARKETPLACE_DATABASE_NAME=minder_marketplace

# Redis
MARKETPLACE_REDIS_HOST=redis
MARKETPLACE_REDIS_PORT=6379
MARKETPLACE_REDIS_PASSWORD=your_password

# Security
LICENSE_SECRET=your_secret_key
JWT_SECRET=your_jwt_secret
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=60

# Application
LOG_LEVEL=INFO
ENVIRONMENT=development
MAX_PLUGINS_PER_USER=100
RATE_LIMIT_PER_MINUTE=60
```

## 🧪 Testing

### Unit Tests
```bash
cd services/marketplace
pytest tests/ -v --cov=.
```

### Integration Tests
```bash
# Database testleri
pytest tests/test_database.py -v

# API endpoint testleri
pytest tests/test_api.py -v

# License generation testleri
pytest tests/test_licensing.py -v
```

### Manual Testing
```bash
# Health check
curl http://localhost:8002/health

# Plugin listesi
curl http://localhost:8002/v1/marketplace/plugins

# Lisans aktivasyonu
curl -X POST http://localhost:8002/v1/marketplace/licenses/activate \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "00000000-0000-0000-0000-000000000001",
    "plugin_id": "550e8400-e29b-41d4-a716-446655440002",
    "tier": "community"
  }'
```

## 📈 Monitoring

### Health Check Endpoint
```bash
curl http://localhost:8002/health
```

Response:
```json
{
  "status": "healthy",
  "service": "marketplace",
  "version": "1.0.0",
  "environment": "development"
}
```

### Metrics (Prometheus)
Servisler Prometheus metrics export eder:
- `marketplace_http_requests_total`
- `marketplace_http_request_duration_seconds`
- `marketplace_database_connections`
- `marketplace_license_validations_total`

## 🛠️ Troubleshooting

### Servis Başlamıyor
```bash
# Logları kontrol et
docker logs minder-marketplace

# Environment variables kontrol et
docker exec minder-marketplace env | grep MARKETPLACE

# Database bağlantısı test et
docker exec minder-postgres psql -U minder -d minder_marketplace -c "SELECT 1;"
```

### API Yanıt Vermiyor
```bash
# Servis durumunu kontrol et
docker ps --filter "name=minder-marketplace"

# Health check
curl http://localhost:8002/health

# API documentation erişimi
curl http://localhost:8002/docs
```

### Database Hataları
```bash
# Tabloları kontrol et
docker exec minder-postgres psql -U minder -d minder_marketplace -c "\dt"

# Migration durumunu kontrol et
docker exec minder-postgres psql -U minder -d minder_marketplace -c "SELECT * FROM marketplace_plugins;"
```

## 📚 Dokümantasyon

- [API Status](docs/API_STATUS.md) - Canlı sistem durumu
- [Database Schema](docs/DATABASE_SCHEMA.md) - Veritabanı yapısı
- [API Endpoints](docs/API_ENDPOINTS.md) - Tüm endpoint detayları
- [Deployment Guide](docs/DEPLOYMENT.md) - Production deployment

## 🤝 Katkıda Bulunma

1. Fork this repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 Lisans

This project is licensed under the MIT License - see the LICENSE file for details.

## 🎯 Roadmap

### v1.1 (Yakında)
- [ ] Web UI geliştirme
- [ ] Otomatik plugin discovery
- [ ] Gelişmiş lisans yönetimi
- [ ] Analytics dashboard

### v2.0 (Gelecek)
- [ ] Multi-tenant support
- [ ] Plugin sandboxing
- [ ] AI-powered plugin recommendations
- [ ] Blockchain-based license verification

---

**Made with ❤️ by the Minder Team**
