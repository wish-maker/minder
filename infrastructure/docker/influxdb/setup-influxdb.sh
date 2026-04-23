#!/bin/bash
# InfluxDB 2.x Initial Setup Script
# Creates organization, bucket, and auth token

set -e

INFLUX_URL="http://localhost:8086"
INFLUX_ADMIN_USER="admin"
INFLUX_ADMIN_PASSWORD="${INFLUXDB_ADMIN_PASSWORD:-minderadmin123}"
INFLUX_ORG="minder"
INFLUX_BUCKET="minder-metrics"
INFLUX_TOKEN="${INFLUXDB_TOKEN:-minder-super-secret-token-change-me}"
INFLUX_RETENTION="30d"

echo "🔧 Setting up InfluxDB 2.x..."

# Wait for InfluxDB to be ready
echo "⏳ Waiting for InfluxDB to start..."
until curl -f ${INFLUX_URL}/health -s >/dev/null 2>&1; do
    echo "   Waiting for ${INFLUX_URL}..."
    sleep 3
done

echo "✅ InfluxDB is ready!"

# Check if setup is already done
if curl -s ${INFLUX_URL}/api/v2/setup -s | grep -q '"allowed":false'; then
    echo "⚠️  InfluxDB already setup, skipping..."
    exit 0
fi

# Perform initial setup
echo "🔐 Setting up InfluxDB authentication..."

curl -s -X POST ${INFLUX_URL}/api/v2/setup \
  -H "Content-Type: application/json" \
  -d "{
    \"username\": \"${INFLUX_ADMIN_USER}\",
    \"password\": \"${INFLUX_ADMIN_PASSWORD}\",
    \"org\": \"${INFLUX_ORG}\",
    \"bucket\": \"${INFLUX_BUCKET}\",
    \"token\": \"${INFLUX_TOKEN}\"
  }"

# Create additional buckets with retention policies
echo "📦 Creating additional buckets..."

# Login and create buckets
influx setup \
  --host ${INFLUX_URL} \
  --username ${INFLUX_ADMIN_USER} \
  --password ${INFLUX_ADMIN_PASSWORD} \
  --org ${INFLUX_ORG} \
  --bucket ${INFLUX_BUCKET} \
  --token ${INFLUX_TOKEN} \
  --force || echo "Setup already completed"

# Create buckets with different retention periods
influx bucket create \
  --org ${INFLUX_ORG} \
  --name minder-metrics-raw \
  --retention 7d \
  --token ${INFLUX_TOKEN} || echo "Bucket minder-metrics-raw exists"

influx bucket create \
  --org ${INFLUX_ORG} \
  --name minder-metrics-downsampled \
  --retention 365d \
  --token ${INFLUX_TOKEN} || echo "Bucket minder-metrics-downsampled exists"

echo ""
echo "✅ InfluxDB setup complete!"
echo ""
echo "📋 Connection Details:"
echo "   URL:      ${INFLUX_URL}"
echo "   Org:      ${INFLUX_ORG}"
echo "   Bucket:   ${INFLUX_BUCKET}"
echo "   Token:    ${INFLUX_TOKEN}"
echo ""
echo "🔑 Save this token for Telegraf and Grafana configuration!"
echo ""
