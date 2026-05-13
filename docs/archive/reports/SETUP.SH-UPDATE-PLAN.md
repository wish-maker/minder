# Setup.sh Güncelleme Planı ve Mevcut Durum Dokümantasyonu

**Tarih**: 6 Mayıs 2026, 21:45
**Durum**: ⚠️ YAML Validation Error - Manuel Container Yönetimi Aktif

---

## 🎯 Mevcut Durum

### Sistem Durumu
```
Toplam Container: 31
Healthy: 27 (%87)
Unhealthy: 1 (neo4j - startup issue)
Network: docker_minder-network
```

### Kullanılan Yöntem
- ❌ Docker Compose: YAML validation error (duplicate keys)
- ✅ Manuel Docker Run: Tüm container'lar manuel başlatıldı

---

## 🔧 Docker Secrets Durumu

### Generated Secrets (.secrets/ dizini)
```
✅ postgres_password.secret       (PostgreSQL için kullanımda)
✅ redis_password.secret          (Redis için kullanımda)
✅ rabbitmq_password.secret       (RabbitMQ için kullanımda)
✅ jwt_secret.secret              (API-Gateway için kullanımda)
✅ webui_secret_key.secret        (OpenWebUI için kullanımda)
✅ grafana_password.secret        (Grafana için kullanımda)
✅ influxdb_admin_password.secret (InfluxDB için kullanımda)
✅ influxdb_token.secret          (InfluxDB için kullanımda)
✅ authelia_jwt_secret.secret     (Authelia için kullanımda)
✅ authelia_storage_encryption_key.secret (Authelia için kullanımda)
⏳ authelia_session_secret.secret (Kullanılmadı)
⏳ minio_root_password.secret     (MinIO çalışmıyor)
```

### Permissions
- Production: 600 (sadece owner)
- Container non-root için: 644 (Grafana durumunda)

---

## 📋 Setup.sh'a Eklenmesi Gerekenler

### 1. Secret Generation Fonksiyonu

```bash
generate_secrets() {
    local secrets_dir="${SCRIPT_DIR}/.secrets"
    
    echo "🔐 Generating secrets..."
    mkdir -p "$secrets_dir"
    
    # Generate 12 secrets
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/postgres_password.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/redis_password.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/rabbitmq_password.secret"
    openssl rand -base64 85 | tr -d '=+/' | head -c 85 > "$secrets_dir/jwt_secret.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/webui_secret_key.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/grafana_password.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/influxdb_admin_password.secret"
    openssl rand -base64 64 | tr -d '=+/' | head -c 64 > "$secrets_dir/influxdb_token.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/authelia_jwt_secret.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/authelia_session_secret.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/authelia_storage_encryption_key.secret"
    openssl rand -base64 32 | tr -d '=+/' | head -c 32 > "$secrets_dir/minio_root_password.secret"
    
    # Set permissions
    chmod 600 "$secrets_dir"/*.secret
    
    echo "✅ Secrets generated in $secrets_dir"
}
```

### 2. Manuel Docker Run Modu

```bash
# Environment variable ile kontrol
if [[ "${MINDER_USE_MANUAL_DOCKER:-}" == "true" ]]; then
    start_services_manually
else
    start_services_with_compose
fi
```

### 3. Container Name Düzeltmeleri

**Sorun**: Docker Compose service isimleri ile manuel container isimleri farklı

**Docker Compose**:
- `redis` → Container adı: `minder-redis`
- `postgres` → Container adı: `minder-postgres`

**Çözüm**:
```bash
# Environment variables'da container name kullan
REDIS_HOST=minder-redis  # DOĞRU
REDIS_HOST=redis          # YANLIŞ (compose için)

POSTGRES_HOST=minder-postgres  # DOĞRU
POSTGRES_HOST=postgres        # YANLIŞ (compose için)
```

### 4. Entrypoint Script'ler

**Authelia**: V4 format migration
```bash
# infrastructure/docker/authelia/entrypoint.sh
#!/bin/bash
set -e

# Load secrets from files
if [ -f /secrets/postgres_password ]; then
    export AUTHELIA_STORAGE_POSTGRES_PASSWORD=$(cat /secrets/postgres_password)
fi

if [ -f /secrets/authelia_storage_encryption_key ]; then
    export AUTHELIA_STORAGE_ENCRYPTION_KEY=$(cat /secrets/authelia_storage_encryption_key)
fi

if [ -f /secrets/authelia_jwt_secret ]; then
    export AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET=$(cat /secrets/authelia_jwt_secret)
fi

exec /authelia --config /config/configuration.yml "$@"
```

**RabbitMQ**: v3.13 _FILE desteği yok
```bash
# infrastructure/docker/rabbitmq/entrypoint.sh
#!/bin/bash
set -e

# Read password from secret
if [ -f /run/secrets/rabbitmq_password ]; then
    RABBITMQ_PASSWORD=$(cat /run/secrets/rabbitmq_password)
else
    echo "ERROR: RabbitMQ password secret not found!"
    exit 1
fi

# Set the password as environment variable
export RABBITMQ_DEFAULT_PASS="$RABBITMQ_PASSWORD"

# Start RabbitMQ
exec /usr/local/bin/docker-entrypoint.sh rabbitmq-server
```

### 5. PostgreSQL Password Sync

**Sorun**: Secret file değişince database内部的password değişmiyor

**Çözüm**:
```bash
sync_postgres_password() {
    local password_file="${SCRIPT_DIR}/.secrets/postgres_password.secret"
    local new_password=$(cat "$password_file")
    
    echo "🔄 Syncing PostgreSQL password..."
    
    # PostgreSQL container çalışıyorsa password'u güncelle
    if docker ps | grep -q minder-postgres; then
        docker exec minder-postgres psql -U minder -d minder -c \
            "ALTER USER minder PASSWORD '$new_password';"
        echo "✅ PostgreSQL password synced"
    fi
}
```

---

## 🚀 Setup.sh Ekleme Planı

### Phase 1: Secret Management (YENİ)
```bash
# Yeni fonksiyonlar
generate_secrets()          # .secrets/ dizinini oluştur
sync_postgres_password()    # PostgreSQL password sync
verify_secrets()             # Secret file kontrolü

# setup.sh start öncesi
generate_secrets            # Otomatik secret generation
```

### Phase 2: Manuel Docker Modu (YENİ)
```bash
# Yeni fonksiyon
start_services_manually()   # Docker compose yerine manuel docker run
stop_services_manually()    # Manuel container'ları durdur
restart_service()           # Tek servis restart (manuel modda)

# Yeni environment variable
MINDER_USE_MANUAL_DOCKER=true  # Manuel modu aktif et
```

### Phase 3: Container Name Fixes
```bash
# Tüm environment variable'larda güncelleme
REDIS_HOST=minder-redis
POSTGRES_HOST=minder-postgres
RABBITMQ_HOST=minder-rabbitmq
```

### Phase 4: Image Version Updates
```bash
# Mevcut working versions
postgres:17.4-alpine        # (v16'dan upgrade edildi)
redis:7.2.13-alpine         # (Mevcut)
rabbitmq:3.13.7-management-alpine  # (Mevcut)
authelia:4.38.7-alpine       # (Mevcut)
```

---

## 📊 Mevcut Container Configuration'ları

### Kritik Değişiklikler

#### 1. PostgreSQL
```yaml
ESKİ: postgres:16
YENİ: postgres:17.4-alpine
Sebep: Data directory v17 ile initialize edilmiş

Environment:
- POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password ✅
- Container name: minder-postgres (manual)
```

#### 2. Redis
```yaml
Image: redis:7.2.13-alpine
Command: redis-server --requirepass "$(cat /run/secrets/redis_password)"
Mount: /root/minder/.secrets/redis_password.secret:/run/secrets/redis_password:ro
Container name: minder-redis (manual)
```

#### 3. RabbitMQ
```yaml
Image: rabbitmq:3.13.7-management-alpine
Entrypoint: /root/minder/infrastructure/docker/rabbitmq/entrypoint.sh
Mount: /root/minder/.secrets/rabbitmq_password.secret:/run/secrets/rabbitmq_password:ro
Environment: RABBITMQ_DEFAULT_PASS (entrypoint tarafından set edilir)
Container name: minder-rabbitmq (manual)
```

#### 4. Authelia
```yaml
Image: authelia:4.38.7-alpine
Mount: /root/minder/.secrets:/secrets:ro
Environment:
  - AUTHELIA_STORAGE_POSTGRES_PASSWORD_FILE=/secrets/postgres_password ✅
  - AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE=/secrets/authelia_storage_encryption_key ✅
  - AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE=/secrets/authelia_jwt_secret ✅
```

#### 5. API-Gateway
```yaml
Image: minder/api-gateway:1.0.0
Environment:
  - REDIS_HOST=minder-redis ✅ (container name)
  - REDIS_PASSWORD=<from secret> ✅
  - POSTGRES_HOST=minder-postgres ✅
  - POSTGRES_PASSWORD=<from secret> ✅
  - JWT_SECRET=<strong 85-char> ✅
```

#### 6. OpenWebUI
```yaml
Image: ghcr.io/open-webui/open-webui:latest
Environment:
  - WEBUI_SECRET_KEY=<from secret> ✅
  - JWT_SECRET=<from secret> ✅
```

---

## ⚠️ Bilinen Sorunlar ve Çözümleri

### 1. YAML Validation Error
**Sorun**: `docker compose config` fails
```
yaml: construct errors:
  line 259: mapping key "volumes" already defined at line 219
  line 285: mapping key "networks" already defined at line 245
```

**Geçici Çözüm**: Manuel docker run kullanılıyor
**Kalıcı Çözüm**: Docker Compose v2 downgrade YA da docker-compose.yml'i minimal recreate

### 2. Schema-Registry PostgreSQL Connection
**Sorun**: Password authentication failed
**Çözüm**: 
1. PostgreSQL password update: `ALTER USER minder PASSWORD '...'`
2. PostgreSQL restart
3. Schema-Registry hostname: minder-postgres (not postgres)

### 3. RabbitMQ-Exporter
**Sorun**: kbudde/rabbitmq-exporter image
**Çözüm**: Doğru image ile başlatma + secret password

### 4. API-Gateway Redis Connection
**Sorun**: "redis" hostname resolution failed
**Çözüm**: REDIS_HOST=minder-redis (container name)

---

## 🎯 Setup.sh Güncelleme Öncelik Sırası

### Priority 1: Secret Management (ACİL)
1. ✅ generate_secrets() fonksiyonu ekle
2. ✅ Secret file permissions (600/644)
3. ✅ sync_postgres_password() fonksiyonu

### Priority 2: Manuel Docker Modu (ACİL)
1. ✅ start_services_manually() fonksiyonu
2. ✅ MINDER_USE_MANUAL_DOCKER environment variable
3. ✅ Container name fixes (minder-redis vs redis)

### Priority 3: Entrypoint Scripts (YAPILACAK)
1. ✅ Authelia entrypoint.sh (v4 migration)
2. ✅ RabbitMQ entrypoint.sh (_FILE workaround)

### Priority 4: Docker Compose Fix (ORTA)
1. YAML validation error çözümü
2. Ya da manuel docker run'i kalıcı hale getirme

---

## 📝 Yapılması Gereken Değişiklikler

### setup.sh'a Eklenecek Fonksiyonlar

```bash
# Secret generation
generate_secrets() {
    # .secrets/ dizini oluştur
    # 12 secret oluştur
    # Permissions set et
}

# PostgreSQL password sync
sync_postgres_password() {
    # Database password'u secret file ile senkronize et
}

# Manuel docker run
start_services_manually() {
    # Tüm servisleri manuel docker run ile başlat
    # Doğru container isimlerini kullan
    # Secret file'ları mount et
}

# Tek servis restart
restart_service() {
    # Manuel modda tek servis restart
    # Container'ı durdur, secret'leri yeniden yükle, başlat
}
```

### Değiştirilecek Fonksiyonlar

```bash
# start_services() - MANUEL DOCKER DESTEK
start_services() {
    if [[ "${MINDER_USE_MANUAL_DOCKER:-}" == "true" ]]; then
        start_services_manually
    else
        docker compose up -d
    fi
}

# stop_services() - MANUEL DOCKER DESTEK
stop_services() {
    if [[ "${MINDER_USE_MANUAL_DOCKER:-}" == "true" ]]; then
        stop_services_manually
    else
        docker compose down
    fi
}
```

---

## 🚀 Sonraki Adımlar

### Acil (Bugün)
1. ✅ Mevcut durum dokümante et
2. ⏳ setup.sh'a secret generation ekle
3. ⏳ setup.sh'a manuel docker modu ekle

### Kısa Vadede (Bu Hafta)
1. setup.sh güncelle
2. Test et: ./setup.sh stop && ./setup.sh start
3. Docker compose fix YA da manuel modu kalıcı hale getir

### Orta Vadede
1. YAML validation error çözümü
2. Production deployment test
3. Full backup/restore test

---

## 💡 Önemli Notlar

1. **Setup.sh Kritik**: Tüm kurulum/kaldırma setup.sh ile olacak
2. **Secretler Korunmalı**: .secrets/ dizini .gitignore'a ekle
3. **Password Sync Critical**: PostgreSQL password'u secret file ile senkronize et
4. **Container Name Mismatch**: Docker Compose service names ≠ Manual container names
5. **Entrypoint Scripts Gerekli**: Authelia ve RabbitMQ için özel script'ler

---

**Dokümante**: Mevcut Durum ve Setup.sh Güncelleme Planı
**Son Güncelleme**: 2026-05-06 21:45
**Durum**: Plan hazır, implementasyon bekliyor
