# 🔐 Secrets Management Guide

## Overview

Minder projesinde güvenlik için çok katmanlı secrets yönetimi kullanılır.

## Environment Variables

### Local Development

1. `.env.example` dosyasını kopyalayın:
```bash
cp .env.example .env
```

2. `.env` dosyasını düzenleyin ve değerleri girin

3. **ÖNEMLİ**: `.env` dosyasını asla commit etmeyin! (.gitignore'da)

### Production (Docker Compose)

Docker Compose `.env` dosyasından otomatik okur:

```yaml
services:
  minder-api:
    env_file:
      - .env
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
```

### CI/CD (GitHub Actions)

GitHub Secrets kullanın:

```yaml
- name: Deploy
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}
```

## GitHub Secrets Yapılandırması

### Gerekli Secrets

Repository Settings → Secrets and variables → Actions bölümüne ekleyin:

1. **GITHUB_TOKEN**
   - Amaç: GitHub API erişimi
   - Oluştur: https://github.com/settings/personal-access-tokens
   - Scope: repo, read:org

2. **DOCKER_USERNAME**
   - Amaç: Docker Hub erişimi
   - Değer: Docker Hub kullanıcı adınız

3. **DOCKER_PASSWORD**
   - Amaç: Docker Hub token
   - Oluştur: https://hub.docker.com/settings/security

4. **JWT_SECRET_KEY**
   - Amaç: API authentication
   - Oluştur: `openssl rand -hex 32`

5. **POSTGRES_PASSWORD**
   - Amaç: Veritabanı şifresi
   - Değer: Güçlü şifre (min 16 karakter)

## Security Best Practices

### 1. Minimum Permission Principle

- Token'ları sadece gerekli scope ile oluşturun
- Production'da admin tokenları kullanmayın

### 2. Token Rotation

- Tokenları düzenli olarak yenileyin (90 gün önerilir)
- Eski tokenları hemen iptal edin

### 3. Environment Specific Secrets

- Development, Staging, Production için ayrı secrets
- Asla environment'lar arası secret paylaşımı yapmayın

### 4. Audit Logging

- Kim hangi secret'e ne zaman erişti?
- Secret değişikliklerini loglayın

## Troubleshooting

### "Invalid credentials" hatası

✅ **Çözüm**:
1. Token'ın süresi geçmiş mi kontrol edin
2. doğru secret'i kullandığınızdan emin olun
3. Token scope'larını kontrol edin

### Container başlamıyor

✅ **Çözüm**:
1. `.env` dosyasının varlığını kontrol edin
2. Environment variable'ların doğru set edildiğini kontrol edin
3. `docker-compose config` ile yapılandırmasını görüntüleyin

## Checklist

- [ ] `.env.example` mevcut
- [ ] `.env` dosyası `.gitignore`'da
- [ ] GitHub Secrets yapılandırıldı
- [ ] Token rotation planı var
- [ ] Audit logging aktif
- [ ] Team eğitimi tamamlandı

## İletişim

Sorularınız için: https://github.com/wish-maker/minder-core/issues
