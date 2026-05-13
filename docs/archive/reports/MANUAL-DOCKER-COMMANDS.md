# Manuel Docker Başlatma Komutları - Mevcut Çalışan Sistem
**Tarih**: 6 Mayıs 2026, 21:50
**Durum**: ✅ Tüm servisler çalışıyor (27/31 healthy)

---

## 🔴 ÖNEMLİ: Docker Compose yerine Manuel Docker Run Kullanılıyor

**Sebep**: docker-compose.yml YAML validation error var
```
yaml: construct errors:
  line 259: mapping key "volumes" already defined at line 219
  line 285: mapping key "networks" already defined at line 245
```

**Geçici Çözüm**: Tüm servisler manuel docker run ile başlatıldı

---

## 📋 Servis Başlatma Sırası

### 1. Network Creation
```bash
docker network create docker_minder-network
```

### 2. Secrets Generation (.secrets/ dizini oluştur)
```bash
mkdir -p .secrets
cd .secrets

# Generate 12 secrets
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > postgres_password.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > redis_password.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > rabbitmq_password.secret
openssl rand -base64 85 | tr -d '=+/' | head -c 85 > jwt_secret.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > webui_secret_key.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > grafana_password.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > influxdb_admin_password.secret
openssl rand -base64 64 | tr -d '=+/' | head -c 64 > influxdb_token.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > authelia_jwt_secret.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > authelia_session_secret.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > authelia_storage_encryption_key.secret
openssl rand -base64 32 | tr -d '=+/' | head -c 32 > minio_root_password.secret

# Set permissions
chmod 600 *.secret
```

### 3. Core Services (Bağımlılık sırasıyla)

#### PostgreSQL
```bash
docker run -d \
  --name minder-postgres \
  --network docker_minder-network \
  -v docker_postgres_data:/var/lib/postgresql/data \
  -v /root/minder/infrastructure/docker/postgres-init.sql:/docker-entrypoint-initdb.d/init.sql:ro \
  -v /root/minder/.secrets/postgres_password.secret:/run/secrets/postgres_password:ro \
  -e POSTGRES_USER=minder \
  -e POSTGRES_MULTIPLE_DATABASES=tefas_db,weather_db,news_db,crypto_db \
  -e POSTGRES_DB=minder \
  -e POSTGRES_PASSWORD_FILE=/run/secrets/postgres_password \
  --health-cmd="pg_isready -U minder -d minder" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=5 \
  postgres:17.4-alpine

# Password sync (sonra gerekli olabilir)
docker exec minder-postgres psql -U minder -d minder -c "ALTER USER minder PASSWORD 'PLgbaoxmXWFumpSlY3aMJX5D7zN5idae';"
```

#### Redis
```bash
docker run -d \
  --name minder-redis \
  --network docker_minder-network \
  -v docker_redis_data:/data \
  -v /root/minder/.secrets/redis_password.secret:/run/secrets/redis_password:ro \
  redis:7.2.13-alpine \
  sh -c 'redis-server --appendonly yes --requirepass "$(cat /run/secrets/redis_password)" --masterauth "$(cat /run/secrets/redis_password)"'
```

#### RabbitMQ
```bash
docker run -d \
  --name minder-rabbitmq \
  --network docker_minder-network \
  -v docker_rabbitmq_data:/var/lib/rabbitmq \
  -v /root/minder/.secrets/rabbitmq_password.secret:/run/secrets/rabbitmq_password:ro \
  -v /root/minder/infrastructure/docker/rabbitmq/entrypoint.sh:/entrypoint.sh:ro \
  -e RABBITMQ_CONFIG_FILE=/etc/rabbitmq/rabbitmq.conf \
  -e RABBITMQ_LOGS=- \
  -e RABBITMQ_LOG_LEVEL=info \
  -e RABBITMQ_DEFAULT_USER=minder \
  --entrypoint=/entrypoint.sh \
  --health-cmd="rabbitmq-diagnostics -q ping" \
  --health-interval=30s \
  --health-timeout=30s \
  --health-retries=3 \
  rabbitmq:3.13.7-management-alpine
```

#### Authelia (SSO/2FA)
```bash
docker run -d \
  --name minder-authelia \
  --network docker_minder-network \
  -v /root/minder/.secrets:/secrets:ro \
  -v /root/minder/infrastructure/docker/authelia/configuration.yml:/config/configuration.yml:ro \
  -v /root/minder/infrastructure/docker/authelia/users_database.yml:/config/users_database.yml:ro \
  -v docker_authelia_data:/config \
  -e AUTHELIA_STORAGE_POSTGRES_PASSWORD_FILE=/secrets/postgres_password \
  -e AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE=/secrets/authelia_storage_encryption_key \
  -e AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE=/secrets/authelia_jwt_secret \
  --health-cmd="curl -f http://localhost:9091 | grep 'OK' || exit 1" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=5 \
  authelia:4.38.7-alpine
```

### 4. Monitoring Services

#### Grafana
```bash
docker run -d \
  --name minder-grafana \
  --network docker_minder-network \
  -v docker_grafana_data:/var/lib/grafana \
  -v /root/minder/infrastructure/docker/grafana/dashboards:/etc/grafana/provisioning/dashboards:ro \
  -v /root/minder/infrastructure/docker/grafana/datasources:/etc/grafana/provisioning/datasources:ro \
  -v /root/minder/.secrets/grafana_password.secret:/run/secrets/grafana_password:ro \
  -e GF_SECURITY_ADMIN_PASSWORD__FILE=/run/secrets/grafana_password \
  -e GF_SERVER_ROOT_URL=https://grafana.minder.local \
  -e GF_INSTALL_PLUGINS= \
  --health-cmd="wget --no-verbose --tries=1 --spider http://localhost:3000/api/health" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=5 \
  grafana/grafana:11.3.1
```

#### InfluxDB
```bash
docker run -d \
  --name minder-influxdb \
  --network docker_minder-network \
  -v docker_influxdb_data:/var/lib/influxdb2 \
  -v /root/minder/.secrets/influxdb_admin_password.secret:/run/secrets/influxdb_admin_password:ro \
  -v /root/minder/.secrets/influxdb_token.secret:/run/secrets/influxdb_token:ro \
  -e DOCKER_INFLUXDB_INIT_MODE=setup \
  -e DOCKER_INFLUXDB_INIT_USERNAME=admin \
  -e DOCKER_INFLUXDB_INIT_ORG=minder \
  -e DOCKER_INFLUXDB_INIT_BUCKET=minder-metrics \
  -e DOCKER_INFLUXDB_INIT_RETENTION=30d \
  -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN_FILE=/run/secrets/influxdb_token \
  -e DOCKER_INFLUXDB_INIT_PASSWORD_FILE=/run/secrets/influxdb_admin_password \
  -e INFLUXDB_LOG_LEVEL=info \
  --health-cmd="influx ping" \
  --health-interval=10s \
  --health-timeout=5s \
  --health-retries=5 \
  influxdb:2.7.12
```

### 5. Application Services

#### API-Gateway
```bash
REDIS_PASS=$(cat /root/minder/.secrets/redis_password.secret)
POSTGRES_PASS=$(cat /root/minder/.secrets/postgres_password.secret)
JWT_SEC=$(cat /root/minder/.secrets/jwt_secret.secret)

docker run -d \
  --name minder-api-gateway \
  --network docker_minder-network \
  -p 8000:8000 \
  -e REDIS_HOST=minder-redis \
  -e REDIS_PORT=6379 \
  -e REDIS_PASSWORD="$REDIS_PASS" \
  -e POSTGRES_HOST=minder-postgres \
  -e POSTGRES_PORT=5432 \
  -e POSTGRES_USER=minder \
  -e POSTGRES_PASSWORD="$POSTGRES_PASS" \
  -e POSTGRES_DB=minder \
  -e JWT_SECRET="$JWT_SEC" \
  -e PLUGIN_REGISTRY_URL=http://minder-plugin-registry:8001 \
  -e RAG_PIPELINE_URL=http://minder-rag-pipeline:8004 \
  -e MODEL_MANAGEMENT_URL=http://minder-model-management:8005 \
  -e RATE_LIMIT_ENABLED=true \
  -e LOG_LEVEL=INFO \
  -e ENVIRONMENT=development \
  --restart unless-stopped \
  --health-cmd="curl -f http://localhost:8000/health || exit 1" \
  --health-interval=30s \
  --health-timeout=10s \
  --health-retries=3 \
  minder/api-gateway:1.0.0
```

#### OpenWebUI
```bash
JWT_SECRET=$(cat /root/minder/.secrets/jwt_secret.secret)
WEBUI_KEY=$(cat /root/minder/.secrets/webui_secret_key.secret)

docker run -d \
  --name minder-openwebui \
  --network docker_minder-network \
  -p 3000:8080 \
  -e WEBUI_SECRET_KEY="$WEBUI_KEY" \
  -e JWT_SECRET="$JWT_SECRET" \
  -e GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D \
  -e OPENAI_API_KEY=${OPENAI_API_KEY:-} \
  -e TIKTOKEN_ENCODING_NAME=cl100k_base \
  -v docker_openwebui_data:/app/backend/data \
  -v /root/minder/infrastructure/docker/openwebui/functions.json:/app/config/functions.json:ro \
  --restart unless-stopped \
  ghcr.io/open-webui/open-webui:latest
```

### 6. Schema Registry
```bash
docker run -d \
  --name minder-schema-registry \
  --network docker_minder-network \
  -e QUARKUS_DATASOURCE_JDBC_URL=jdbc:postgresql://minder-postgres:5432/minder \
  -e QUARKUS_DATASOURCE_USERNAME=minder \
  -e QUARKUS_DATASOURCE_PASSWORD=PLgbaoxmXWFumpSlY3aMJX5D7zN5idae \
  -e REGISTRY_DATASOURCE_URL=jdbc:postgresql://minder-postgres:5432/minder \
  -e REGISTRY_DATASOURCE_USERNAME=minder \
  -e REGISTRY_DATASOURCE_PASSWORD=PLgbaoxmXWFumpSlY3aMJX5D7zN5idae \
  -e QUARKUS_DATASOURCE_DRIVER=org.postgresql.Driver \
  -e REGISTRY_DATASOURCE_DRIVER=org.postgresql.Driver \
  apicurio/apicurio-registry-sql:2.5.7.Final
```

### 7. Exporters

#### RabbitMQ-Exporter
```bash
RABBIT_PASS=$(cat /root/minder/.secrets/rabbitmq_password.secret)

docker run -d \
  --name minder-rabbitmq-exporter \
  --network docker_minder-network \
  -e RABBIT_USER=minder \
  -e RABBIT_PASSWORD="$RABBIT_PASS" \
  -e RABBIT_URL=http://minder:$RABBIT_PASS@minder-rabbitmq:15672 \
  -e PUBLISH_PORT=9419 \
  -e RABBIT_CAPABILITIES=sort,bert \
  --restart unless-stopped \
  kbudde/rabbitmq-exporter:latest
```

---

## 🔑 Kritik Değişiklikler (Docker Compose'a Göre)

### 1. Container Name Değişiklikleri

| Docker Compose Service | Manuel Container Name | Kullanım Yeri |
|------------------------|---------------------|---------------|
| `redis` | `minder-redis` | REDIS_HOST env var |
| `postgres` | `minder-postgres` | POSTGRES_HOST env var |
| `rabbitmq` | `minder-rabbitmq` | RABBITMQ_URL env var |

### 2. Environment Variable Format Değişiklikleri

#### Authelia v4 Format
```bash
# ESKİ (v3):
AUTHELIA_DEFAULT_REDIRECTION_URL=...

# YENİ (v4):
AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE=/secrets/authelia_storage_encryption_key
AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE=/secrets/authelia_jwt_secret
```

#### RabbitMQ Password
```bash
# ESKİ:
RABBITMQ_DEFAULT_PASS_FILE=/run/secrets/rabbitmq_password  # DEPRECATED!

# YENİ (entrypoint script ile):
RABBITMQ_DEFAULT_PASS (entrypoint tarafından set ediliyor)
```

### 3. Image Version Değişiklikleri

```bash
# PostgreSQL:
postgres:16 → postgres:17.4-alpine  # Data directory v17 ile initialize edilmiş

# Schema-Registry:
apicurio/apicurio-registry-mem → apicurio/apicurio-registry-sql:2.5.7.Final

# RabbitMQ-Exporter:
prometheuscommunity/postgres-exporter:v0.15.0 → kbudde/rabbitmq-exporter:latest
```

---

## 📝 Setup.sh'a Eklenmesi Gereken Kod Parçacıkları

### 1. Secret Generation Fonksiyonu

```bash
generate_secrets() {
    local secrets_dir="${SCRIPT_DIR}/.secrets"
    
    log_step "Generating secrets"
    
    # Create secrets directory
    mkdir -p "$secrets_dir"
    
    # Generate 12 secrets
    log_detail "Generating 12 secrets in $secrets_dir"
    
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
    
    # Grafana için 644 (non-root container user)
    chmod 644 "$secrets_dir/grafana_password.secret"
    
    log_success "Secrets generated in $secrets_dir"
    log_detail "Permissions: 600 (grafana: 644)"
}
```

### 2. Manuel Docker Run Fonksiyonu (Basitleştirilmiş)

```bash
start_services_manually() {
    log_step "Starting services manually (docker run)"
    
    # Check if secrets exist
    if [[ ! -d "${SCRIPT_DIR}/.secrets" ]]; then
        log_error "Secrets not found. Run: ./setup.sh generate-secrets"
        exit 1
    fi
    
    # Load secrets
    local postgres_pass=$(cat "${SCRIPT_DIR}/.secrets/postgres_password.secret")
    local redis_pass=$(cat "${SCRIPT_DIR}/.secrets/redis_password.secret")
    local rabbitmq_pass=$(cat "${SCRIPT_DIR}/.secrets/rabbitmq_password.secret")
    local jwt_secret=$(cat "${SCRIPT_DIR}/.secrets/jwt_secret.secret")
    local webui_key=$(cat "${SCRIPT_DIR}/.secrets/webui_secret_key.secret")
    local grafana_pass=$(cat "${SCRIPT_DIR}/.secrets/grafana_password.secret")
    local influxdb_pass=$(cat "${SCRIPT_DIR}/.secrets/influxdb_admin_password.secret")
    local influxdb_token=$(cat "${SCRIPT_DIR}/.secrets/influxdb_token.secret")
    local authelia_jwt=$(cat "${SCRIPT_DIR}/.secrets/authelia_jwt_secret.secret)
    local authelia_enc=$(cat "${SCRIPT_DIR}/.secrets/authelia_storage_encryption_key.secret")
    
    # Core services
    log_detail "Starting core services..."
    # PostgreSQL, Redis, RabbitMQ, Authelia komutları buraya...
    
    # Monitoring services
    log_detail "Starting monitoring services..."
    # Grafana, InfluxDB komutları buraya...
    
    # Application services
    log_detail "Starting application services..."
    # API-Gateway, OpenWebUI komutları buraya...
    
    log_success "All services started"
}
```

### 3. Container Name Environment Variable Düzeltmeleri

```bash
# API-Gateway için doğru hostname'ler
-e REDIS_HOST=minder-redis \      # DOĞRU (container name)
# -e REDIS_HOST=redis \          # YANLIŞ (compose service name)

# Diğer servisler için benzer düzeltmeler
-e POSTGRES_HOST=minder-postgres \
-e RABBITMQ_HOST=minder-rabbitmq \
```

---

## 🚀 Kullanım Örnekleri

### Tüm Servisleri Başlatma
```bash
# 1. Secrets oluştur
./setup.sh generate-secrets

# 2. Manuel modda başlat
MINDER_USE_MANUAL_DOCKER=true ./setup.sh start

# Ya da doğrudan
./setup.sh start  # Otomatik olarak manuel modu kullanacak (YAML error nedeniyle)
```

### Tek Servis Restart
```bash
# Örnek: Redis restart
docker stop minder-redis
docker rm minder-redis
# Redis komutunu tekrar çalıştır
```

### Sistemi Durdurma
```bash
./setup.sh stop  # Tüm container'ları durdur
```

### Sistemi Temizleme
```bash
./setup.sh clean  # Tüm container'ları ve volume'ları sil
```

---

## ⚠️ Dikkat Edilmesi Gerekenler

1. **Secret Permissions**: .secrets/ dizini .gitignore'a ekle
2. **PostgreSQL Password**: Secret değişince database'de manuel ALTER USER gerekiyor
3. **Container Names**: Docker Compose service names ≠ Manuel container names
4. **Entrypoint Scripts**: Authelia ve RabbitMQ için özel entrypoint gerekli
5. **Image Versions**: PostgreSQL v17.4, Redis v7.2.13 kullanılıyor

---

**Dokümante**: Manuel Docker Başlatma Komutları
**Son Güncelleme**: 2026-05-06 21:50
**Durum**: Mevcut sistem - tüm servisler çalışıyor
