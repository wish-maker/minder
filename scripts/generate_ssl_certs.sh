#!/bin/bash
#
# Generate SSL certificates for production deployment
# For production, use Let's Encrypt or proper CA certificates
#

set -e

# Configuration
DOMAIN=${1:-"api.minder.example.com"}
COUNTRY=${2:-"US"}
STATE=${3:-"California"}
CITY=${4:-"San Francisco"}
ORG=${5:-"FundMind AI"}

echo "=================================================="
echo "SSL CERTIFICATE GENERATION"
echo "=================================================="
echo "Domain: $DOMAIN"
echo "Organization: $ORG"
echo ""

# Create SSL directory
SSL_DIR="./nginx/ssl"
mkdir -p "$SSL_DIR"

# Generate private key
echo "1. Generating private key..."
openssl genrsa -out "$SSL_DIR/minder.key" 4096

# Generate certificate signing request
echo "2. Generating certificate signing request..."
openssl req -new -key "$SSL_DIR/minder.key" \
  -out "$SSL_DIR/minder.csr" \
  -subj "/C=$COUNTRY/ST=$STATE/L=$CITY/O=$ORG/CN=$DOMAIN"

# Generate self-signed certificate (valid for 1 year)
echo "3. Generating self-signed certificate..."
openssl x509 -req -days 365 \
  -in "$SSL_DIR/minder.csr" \
  -signkey "$SSL_DIR/minder.key" \
  -out "$SSL_DIR/minder.crt"

# Set proper permissions
chmod 600 "$SSL_DIR/minder.key"
chmod 644 "$SSL_DIR/minder.crt"

echo ""
echo "=================================================="
echo "✓ SSL CERTIFICATES GENERATED"
echo "=================================================="
echo "Files created:"
echo "  - $SSL_DIR/minder.key (private key)"
echo "  - $SSL_DIR/minder.crt (certificate)"
echo "  - $SSL_DIR/minder.csr (CSR)"
echo ""
echo "⚠️  WARNING: Self-signed certificates are for testing only!"
echo "For production, use Let's Encrypt:"
echo "  certbot certonly --nginx -d $DOMAIN"
echo ""
echo "To view certificate:"
echo "  openssl x509 -in $SSL_DIR/minder.crt -text -noout"
echo "=================================================="
