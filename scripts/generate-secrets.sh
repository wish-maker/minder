#!/bin/bash
# Minder Platform - Generate Secure Secrets
# This script generates cryptographically secure secrets for production use

set -e

echo "🔐 Generating secure secrets for Minder Platform..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env file already exists
ENV_FILE="infrastructure/docker/.env"
if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}⚠️  Warning: .env file already exists${NC}"
    echo "Creating backup: $ENV_FILE.backup"
    cp "$ENV_FILE" "$ENV_FILE.backup"
    echo ""
fi

# Generate secure passwords using OpenSSL
generate_password() {
    local length=$1
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-${length}
}

# Generate all secrets
echo "📊 Generating secure secrets..."

GRAFANA_PASS=$(generate_password 25)
JWT_SECRET=$(openssl rand -base64 64)
WEBUI_SECRET=$(openssl rand -base64 64)
REDIS_PASS=$(generate_password 25)
POSTGRES_PASS=$(generate_password 25)
INFLUXDB_PASS=$(generate_password 25)
INFLUXDB_TOKEN=$(openssl rand -base64 32 | tr -d "=+/")

echo "✅ Secrets generated"
echo ""

# Create .env file with generated secrets
cat > "$ENV_FILE" << EOF
# Minder Platform - Environment Configuration
# AUTO-GENERATED: $(date)
# ⚠️  NEVER COMMIT THIS FILE TO VERSION CONTROL
# ⚠️  STORE THESE PASSWORDS IN A SECURE PASSWORD MANAGER

# ============================================================================
# DATABASE CONFIGURATION
# ============================================================================

# PostgreSQL Configuration
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=minder
POSTGRES_USER=minder
POSTGRES_PASSWORD=${POSTGRES_PASS}

# ============================================================================
# REDIS CONFIGURATION
# ============================================================================

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=${REDIS_PASS}

# ============================================================================
# INFLUXDB 2.x CONFIGURATION
# ============================================================================

# InfluxDB 2.x Configuration
INFLUXDB_ADMIN_USERNAME=admin
INFLUXDB_ADMIN_PASSWORD=${INFLUXDB_PASS}
INFLUXDB_INIT_ORG=minder
INFLUXDB_INIT_BUCKET=minder-metrics
INFLUXDB_TOKEN=${INFLUXDB_TOKEN}

# ============================================================================
# QDRANT CONFIGURATION
# ============================================================================

QDRANT_HOST=qdrant
QDRANT_PORT=6333

# ============================================================================
# OLLAMA CONFIGURATION
# ============================================================================

OLLAMA_HOST=http://ollama:11434
OLLAMA_PORT=11434
OLLAMA_MODELS=llama3.2,nomic-embed-text
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OLLAMA_LLM_MODEL=llama3.2

# ============================================================================
# WEBUI CONFIGURATION
# ============================================================================

WEBUI_SECRET_KEY=${WEBUI_SECRET}
WEBUI_AUTH=true
ENABLE_SIGNUP=true
DEFAULT_USER_ROLE=user

# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

# JWT Authentication
JWT_SECRET=${JWT_SECRET}
JWT_EXPIRE_MINUTES=30

# Grafana
GRAFANA_ADMIN_PASSWORD=${GRAFANA_PASS}

# Application Settings
ENVIRONMENT=production
LOG_LEVEL=INFO

# Plugin Security
PLUGIN_SECURITY_LEVEL=moderate
PLUGIN_TRUSTED_AUTHORS=
PLUGIN_BLOCKED_AUTHORS=
PLUGIN_REQUIRE_SIGNATURE=false
PLUGIN_MAX_SIZE_MB=10

# Network Configuration
LOCAL_NETWORK_CIDR=192.168.68.0/24
TAILSCALE_CIDR=100.64.0.0/10
TRUST_LOCAL_NETWORK=true
TRUST_VPN_NETWORK=true
ALLOWED_ORIGINS=http://localhost:3000

# ============================================================================
# RATE LIMITING
# ============================================================================

RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=60

EOF

echo "✅ Environment file created: $ENV_FILE"
echo ""

# Set restrictive permissions
chmod 600 "$ENV_FILE"
echo "✅ Permissions set: 600 (read/write for owner only)"
echo ""

# Display generated passwords (WARNING: Only show once)
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${RED}⚠️  IMPORTANT: SAVE THESE PASSWORDS IN A SECURE LOCATION ⚠️${NC}"
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "📋 Generated Credentials:"
echo ""
echo "   Grafana Admin:    ${GRAFANA_PASS}"
echo "   PostgreSQL:       ${POSTGRES_PASS}"
echo "   Redis:            ${REDIS_PASS}"
echo "   InfluxDB Admin:   ${INFLUXDB_PASS}"
echo "   InfluxDB Token:   ${INFLUXDB_TOKEN}"
echo ""
echo -e "${YELLOW}💡 Store these passwords in a password manager (1Password, Bitwarden, etc.)${NC}"
echo -e "${YELLOW}💡 After saving this file, you cannot recover these passwords!${NC}"
echo ""
echo -e "${GREEN}✅ Secrets generation complete!${NC}"
echo ""
echo "🚀 Next steps:"
echo "   1. Review and update infrastructure/docker/.env if needed"
echo "   2. Start the platform: ./setup.sh"
echo "   3. Access Grafana: http://localhost:3000 (admin:${GRAFANA_PASS})"
echo ""
