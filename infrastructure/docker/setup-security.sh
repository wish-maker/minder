#!/bin/bash
# Minder Platform - Security Setup Script
# Generates secure credentials and creates .env file

set -e

echo "🔐 Minder Platform - Security Setup"
echo "===================================="
echo ""

# Check if .env already exists
if [ -f .env ]; then
    read -p ".env file already exists. Overwrite? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "❌ Aborted."
        exit 1
    fi
    mv .env .env.backup.$(date +%Y%m%d_%H%M%S)
    echo "📦 Backed up existing .env file"
fi

# Check if openssl is available
if ! command -v openssl &> /dev/null; then
    echo "❌ Error: openssl is required but not installed."
    echo "   Install with: apt-get install openssl (Ubuntu/Debian)"
    exit 1
fi

echo "🔑 Generating secure credentials..."
echo ""

# Generate PostgreSQL password (32 chars)
POSTGRES_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)

# Generate Redis password (32 chars)
REDIS_PASSWORD=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)

# Generate JWT secret (64 chars)
JWT_SECRET=$(openssl rand -base64 64 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 64)

# Generate InfluxDB token (32 chars)
INFLUXDB_TOKEN=$(openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c 32)

# Create .env file
cat > .env <<EOF
# Minder Platform - Environment Configuration
# Generated: $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# WARNING: Keep this file secure and never commit to git!

POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
JWT_SECRET=${JWT_SECRET}
INFLUXDB_TOKEN=${INFLUXDB_TOKEN}
ENVIRONMENT=production
LOG_LEVEL=INFO
EOF

echo "✅ .env file created successfully!"
echo ""
echo "🔐 Generated Credentials:"
echo "   PostgreSQL Password: ${POSTGRES_PASSWORD:0:16}..."
echo "   Redis Password:      ${REDIS_PASSWORD:0:16}..."
echo "   JWT Secret:          ${JWT_SECRET:0:16}..."
echo "   InfluxDB Token:      ${INFLUXDB_TOKEN:0:16}..."
echo ""
echo "⚠️  IMPORTANT SECURITY NOTES:"
echo "   1. Store .env file securely (permissions: 600)"
echo "   2. Never commit .env to version control"
echo "   3. Back up .env to a secure location"
echo "   4. Rotate credentials quarterly"
echo "   5. Use different values for each environment"
echo ""
echo "📝 Next Steps:"
echo "   1. Review .env file: cat .env"
echo "   2. Set permissions: chmod 600 .env"
echo "   3. Start services: docker compose up -d"
echo "   4. Verify deployment: docker compose ps"
echo ""

# Set restrictive permissions
chmod 600 .env
echo "✅ Set .env file permissions to 600 (read/write for owner only)"
echo ""
echo "🎉 Security setup complete!"
