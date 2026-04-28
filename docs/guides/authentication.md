# Authentication and Security

## Overview

Minder Platform uses enterprise-grade security with Authelia for SSO and 2FA, protected by Traefik reverse proxy.

## Security Architecture

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTPS (Port 443)
┌──────▼──────────────────┐
│      Traefik            │
│  - SSL Termination      │
│  - Request Routing      │
│  - Security Headers     │
└──────┬──────────────────┘
       │ Forward Auth
┌──────▼──────────────────┐
│     Authelia            │
│  - SSO & 2FA            │
│  - Access Control       │
│  - Session Management   │
└──────┬──────────────────┘
       │ Authenticated
┌──────▼──────────────────┐
│   Microservices         │
│  - API Gateway          │
│  - Plugin Registry      │
│  - AI Services          │
└─────────────────────────┘
```

## Components

### Traefik (Reverse Proxy)

**Purpose**: Single entry point, SSL termination, request routing

**Features**:
- Automatic HTTPS with Let's Encrypt
- Load balancing
- Security headers
- Rate limiting
- Forward auth integration

**Access**:
- Dashboard: `http://localhost:8081` (admin only)
- Public: `https://minder.local` (or `http://localhost`)

**Configuration**: `infrastructure/docker/traefik/`

### Authelia (SSO & 2FA)

**Purpose**: Centralized authentication and authorization

**Features**:
- Single Sign-On (SSO)
- Two-Factor Authentication (2FA)
  - TOTP (Google Authenticator, Authy, etc.)
  - WebAuthn (hardware keys, biometrics)
- Brute force protection
- Session management
- Access control rules

**Access**: `https://auth.minder.local` (or `http://localhost:9091`)

**Configuration**: `infrastructure/docker/authelia/`

## Default Users

⚠️ **SECURITY WARNING**: Change these passwords immediately after first login!

| Username | Password | Role | Description |
|----------|----------|------|-------------|
| `admin` | `admin123` | Admin | Full system access |
| `developer` | `admin123` | Developer | API and development access |
| `user` | `admin123` | User | Basic application access |

## Changing Passwords

### Option 1: Via Authelia Configuration

1. Generate Argon2 hashed password:
```bash
docker exec -it minder-authelia authelia hashes password generate \
  --password "your_new_secure_password"
```

2. Update `infrastructure/docker/authelia/users_database.yml`:
```yaml
users:
  admin:
    disabled: false
    displayname: Admin User
    password: "$argon2id$v=19$m=65536,t=4,p=4$..."  # Paste hash here
    email: admin@minder.local
    groups:
      - admins
```

3. Restart Authelia:
```bash
docker compose -f infrastructure/docker/docker-compose.yml restart authelia
```

### Option 2: Via Authelia Portal

1. Access `https://auth.minder.local`
2. Login with current credentials
3. Navigate to Profile → Reset Password
4. Enter new password (minimum 8 characters, uppercase, lowercase, number, special)

## Access Control Rules

### Public URLs (No Authentication)
- `public.minder.local` - Public landing page
- `*/health` - Health check endpoints

### One-Factor Authentication (Password Only)
- `app.minder.local` - Main application
- `registry.minder.local` - Plugin Registry
- `marketplace.minder.local` - Marketplace

### Two-Factor Authentication (Password + 2FA)
- `admin.minder.local` - Admin dashboard
- `api.minder.local` - API Gateway
- All internal microservices

### Admin Only (Admin Group + 2FA)
- `grafana.minder.local` - Grafana monitoring
- `prometheus.minder.local` - Prometheus metrics
- `traefik.minder.local` - Traefik dashboard

## Setting Up 2FA

### TOTP (Time-based One-Time Password)

1. Login to Authelia
2. Navigate to: One-Time Password → Register
3. Scan QR code with your authenticator app:
   - Google Authenticator
   - Authy
   - Microsoft Authenticator
   - 1Password
   - Bitwarden

### WebAuthn (Hardware Keys)

1. Login to Authelia
2. Navigate to: WebAuthn → Register
3. Connect your hardware key:
   - YubiKey
   - Titan Security Key
   - Windows Hello
   - Touch ID

## Domain Configuration

### Local Development

Add to `/etc/hosts` (Linux/Mac) or `C:\Windows\System32\drivers\etc\hosts` (Windows):

```
127.0.0.1  minder.local
127.0.0.1  auth.minder.local
127.0.0.1  api.minder.local
127.0.0.1  admin.minder.local
127.0.0.1  app.minder.local
127.0.0.1  registry.minder.local
127.0.0.1  marketplace.minder.local
127.0.0.1  grafana.minder.local
127.0.0.1  prometheus.minder.local
127.0.0.1  traefik.minder.local
```

### Production DNS

For production, configure DNS records:

```
minder.local           A   <your-server-ip>
auth.minder.local      A   <your-server-ip>
api.minder.local       A   <your-server-ip>
*.minder.local         CNAME minder.local
```

## SMTP Configuration (for Email Notifications)

Authelia can send email notifications for:
- Password reset
- 2FA registration
- Login alerts
- Account changes

### Setup

Edit `infrastructure/docker/.env`:

```bash
# Gmail Example (use App Passwords)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-email@gmail.com
SMTP_PASSWORD=your-app-password  # Generate at Google Account Settings
```

Restart Authelia:
```bash
docker compose -f infrastructure/docker/docker-compose.yml restart authelia
```

## OIDC / OAuth2 Integration

Authelia provides OpenID Connect for applications:

### Configuration

Clients are pre-configured in `infrastructure/docker/authelia/configuration.yml`:

```yaml
identity_providers:
  oidc:
    clients:
      - id: minder-web
        secret: ${OIDC_CLIENT_SECRET_MINDER_WEB}
        redirect_uris:
          - https://public.minder.local/oauth2/callback
```

### Environment Variables

Set in `infrastructure/docker/.env`:

```bash
# Generate with: openssl rand -base64 32
OIDC_CLIENT_SECRET_MINDER_WEB=your-secret-here
OIDC_CLIENT_SECRET_MINDER_API=your-secret-here
```

## Session Management

### Session Duration

- **Default**: 1 hour
- **Inactivity Timeout**: 5 minutes
- **Remember Me**: 1 month

### Configuration

Edit `infrastructure/docker/authelia/configuration.yml`:

```yaml
session:
  expiration: 1h
  inactivity: 5m
  remember_me: 1M
```

### Session Storage

Sessions are stored in Redis for scalability and persistence.

## Brute Force Protection

Authelia automatically bans IPs after:
- **Max Retries**: 5 attempts
- **Find Time**: 2 minutes
- **Ban Time**: 5 minutes

### Configuration

Edit `infrastructure/docker/authelia/configuration.yml`:

```yaml
regulation:
  max_retries: 5
  find_time: 2m
  ban_time: 5m
```

## Troubleshooting

### Cannot Access Services

1. Check Traefik status:
```bash
docker logs minder-traefik
```

2. Check Authelia health:
```bash
curl http://localhost:9091/api/health
```

3. Verify DNS resolution:
```bash
ping minder.local
```

### 2FA Not Working

1. Check system time is synchronized
2. Verify TOTP secret is correct
3. Try backup codes (if configured)

### Session Issues

1. Clear browser cookies for `*.minder.local`
2. Check Redis is healthy:
```bash
docker exec -it minder-redis redis-cli -a ${REDIS_PASSWORD} ping
```

3. Check session storage in Authelia logs:
```bash
docker logs minder-authelia
```

### SSL/TLS Certificate Issues

1. For development, Traefik uses self-signed certs
2. Accept browser warning for `*.minder.local`
3. For production, configure Let's Encrypt:

Edit `infrastructure/docker/traefik/traefik.yml`:
```yaml
certificatesResolvers:
  default:
    acme:
      email: your-email@example.com
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web
```

## Security Best Practices

1. **Change default passwords immediately**
2. **Enable 2FA for all users**
3. **Use strong password policy** (8+ chars, mixed case, numbers, symbols)
4. **Configure SMTP for email notifications**
5. **Regularly update Authelia** (`docker compose pull authelia`)
6. **Monitor access logs**: `docker logs minder-authelia`
7. **Use HTTPS only in production**
8. **Implement IP whitelisting for admin access**
9. **Rotate secrets quarterly**
10. **Backup Redis session data regularly**

## Monitoring

### View Authelia Logs

```bash
# Real-time logs
docker logs -f minder-authelia

# Last 100 lines
docker logs --tail 100 minder-authelia
```

### View Traefik Access Logs

```bash
# Real-time access logs
docker logs -f minder-traefik
```

### Prometheus Metrics

Authelia exposes metrics at:
- `http://authelia:9091/metrics`

Access via Prometheus: `http://localhost:9090`

## Additional Resources

- [Authelia Documentation](https://www.authelia.com/)
- [Traefik Documentation](https://doc.traefik.io/traefik/)
- [Security Best Practices](https://www.authelia.com/guides/security/)
