# Minder Configuration Guide

## Version 1.0.0

Minder uses a **single source of truth** configuration approach:

- **config.yaml**: All non-sensitive configuration
- **.env**: Only secrets and environment-specific values
- **Pydantic**: Type-safe validation via `core/config.py`

---

## Quick Start

### 1. Copy Environment Template

```bash
cp .env.production.example .env
```

### 2. Set Required Secrets

Edit `.env` and set these REQUIRED variables:

```bash
# Generate secure passwords
POSTGRES_PASSWORD=$(openssl rand -base64 24)
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

### 3. Verify Configuration

```bash
# Test configuration loading
python3 -c "from core.config import MinderConfig; config = MinderConfig.load_yaml(); print(config.model_dump_json(indent=2))"
```

### 4. Start Application

```bash
docker-compose up -d
```

---

## Configuration Structure

### config.yaml (Non-Sensitive)

Contains all configuration except secrets:

```yaml
# Database connection
database:
  host: postgres
  port: 5432
  user: postgres

# Plugin settings
plugins:
  tefas:
    enabled: true
    priority: "high"
```

### .env (Secrets Only)

Contains ONLY sensitive data:

```bash
POSTGRES_PASSWORD=secure_password_here
JWT_SECRET_KEY=secure_jwt_key_here
```

---

## Environment Variable Override

You can override ANY config value using environment variables:

```bash
# Override nested values with double underscore
DATABASE__HOST=custom-host
PLUGINS__TEFAS__ENABLED=false
SECURITY__JWT__EXPIRE__MINUTES=60
```

---

## Configuration Validation

Minder uses Pydantic for automatic validation:

```python
from core.config import MinderConfig

# Load and validate
config = MinderConfig.load_yaml()

# Validation errors will raise exceptions automatically
# e.g., "JWT_SECRET_KEY must be at least 32 characters"
```

---

## Database Configuration

Each plugin uses a separate database:

```yaml
database:
  fundmind_db: fundmind      # TEFAS data
  news_db: minder_news        # News articles
  weather_db: minder_weather  # Weather data
  crypto_db: minder_crypto    # Crypto prices
  network_db: minder_network  # Network metrics
```

Get connection config for a specific database:

```python
from core.config import get_config

config = get_config()
news_db_config = config.get_database_config("news")
# Returns: {host, port, database, user, password}
```

---

## Plugin Configuration

All plugins share common settings:

```yaml
plugins:
  tefas:
    enabled: true              # Is plugin active?
    priority: "high"           # high, medium, low
    health_check_interval: 300 # Seconds between health checks
    failure_threshold: 3       # Failures before disable
    auto_restart: true         # Auto-restart on failure
```

Plugin-specific settings:

```yaml
plugins:
  tefas:
    historical_start_date: "2020-01-01"
    fund_types: ["YAT", "EMK", "BYF"]
  
  weather:
    locations: ["Istanbul", "Ankara", "Izmir"]
  
  crypto:
    symbols: ["BTC", "ETH", "USDT"]
    cache_ttl: 300
```

---

## Security Configuration

### JWT Authentication

```yaml
security:
  jwt_secret_key: ""  # Loaded from JWT_SECRET_KEY env var
  jwt_expire_minutes: 30
```

**Requirement**: JWT_SECRET_KEY must be at least 32 characters

### Rate Limiting

Network-aware rate limiting:

```yaml
security:
  rate_limit_local: "unlimited"   # Local network
  rate_limit_vpn: 200             # VPN/Tailscale
  rate_limit_public: 50           # Public internet
```

### CORS

```yaml
security:
  allowed_origins:
    - "http://localhost:3000"
    - "http://192.168.68.*"
```

---

## Plugin Store Configuration

```yaml
plugin_store:
  enabled: true
  store_path: "/var/lib/minder/plugins"
  require_signature: false  # Set to true in production
  allow_unsigned: true
```

**Production Security**:

```yaml
plugin_store:
  require_signature: true
  allow_unsigned: false
  scan_for_malware: true
```

---

## Performance Tuning

```yaml
performance:
  max_workers: 4          # Parallel workers
  batch_size: 100         # Records per batch
  cache_ttl: 3600         # Cache lifetime (1 hour)
  max_event_history: 10000 # Events to keep in memory
```

---

## Monitoring Configuration

```yaml
logging:
  level: "INFO"           # DEBUG, INFO, WARNING, ERROR
  file: "/var/log/minder/minder.log"
  rotation: "daily"       # daily, weekly, monthly
  retention: 30           # Days to keep logs
```

---

## Troubleshooting

### Configuration Not Loading

```bash
# Check file exists
ls -la config.yaml

# Check syntax
python3 -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Check validation
python3 -c "from core.config import MinderConfig; MinderConfig.load_yaml()"
```

### Environment Variables Not Working

```bash
# Check variable is set
echo $POSTGRES_PASSWORD

# Check .env file exists
ls -la .env

# Verify .env format (no spaces around =)
# Correct: POSTGRES_PASSWORD=value
# Wrong: POSTGRES_PASSWORD = value
```

### Pydantic Validation Errors

Common errors and fixes:

```python
# Error: "JWT_SECRET_KEY must be at least 32 characters"
# Fix: Generate longer key
JWT_SECRET_KEY=$(openssl rand -hex 32)

# Error: "database.host field required"
# Fix: Ensure config.yaml has database.host set
```

---

## Best Practices

1. **Never commit .env** to version control
2. **Use strong passwords** (min 16 chars for databases, 32 for JWT)
3. **Rotate secrets** regularly (90 days recommended)
4. **Test configuration** in development before production
5. **Document custom values** for team members
6. **Use environment variables** for deployment-specific settings
7. **Keep config.yaml** in version control (it's non-sensitive)

---

## Migration from Old Config

If you have old config files:

```bash
# 1. Backup old configs
mkdir -p archive/old_config
mv config/*.yml archive/old_config/

# 2. Copy new config
cp config.yaml.example config.yaml

# 3. Update with your values
vim config.yaml

# 4. Create .env from template
cp .env.production.example .env
vim .env

# 5. Verify
python3 -c "from core.config import MinderConfig; print(MinderConfig.load_yaml())"
```

---

## Support

For configuration issues:
- Check logs: `docker-compose logs minder`
- Verify config: `python3 -c "from core.config import MinderConfig; MinderConfig.load_yaml()"`
- Run health check: `curl http://localhost:8000/health`
- See troubleshooting: `docs/TROUBLESHOOTING.md`
