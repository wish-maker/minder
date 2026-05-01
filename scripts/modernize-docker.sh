#!/bin/bash
###############################################################################
# Minder Platform - Docker Infrastructure Modernization Script
# Purpose: Upgrade all Docker images to latest stable versions
###############################################################################

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Version mappings
declare -A VERSION_UPGRADES=(
    # Critical upgrades (breaking changes)
    ["traefik"]="v3.1.6"
    ["grafana"]="11.4.0"

    # Safe upgrades
    ["authelia"]="4.38.7"
    ["redis"]="7.2-alpine"
    ["ollama"]="0.5.7"
    ["qdrant"]="v1.18.0"
    ["neo4j"]="5.24-community"
    ["influxdb"]="2.8.3"
    ["telegraf"]="1.33.1"
    ["prometheus"]="v2.55.1"
    ["alertmanager"]="v0.28.1"
    ["open-webui"]="git-69d0a16"
    ["postgres-exporter"]="v0.15.0"
    ["redis_exporter"]="v1.62.0"

    # Internal services (semantic versioning)
    ["api-gateway"]="1.0.0"
    ["plugin-registry"]="1.0.0"
    ["rag-pipeline"]="1.0.0"
    ["model-management"]="1.0.0"
    ["marketplace"]="1.0.0"
    ["plugin-state-manager"]="2.1.0"
    ["tts-stt-service"]="2.1.0"
    ["model-fine-tuning"]="2.1.0"
)

# PostgreSQL stays at 16 (requires manual migration)
POSTGRES_VERSION="16"

log_info "Starting Docker Infrastructure Modernization..."
log_info "================================================"

# Backup current docker-compose.yml
log_info "Backing up current docker-compose.yml..."
cp infrastructure/docker/docker-compose.yml infrastructure/docker/docker-compose.yml.backup-$(date +%Y%m%d-%H%M%S)
log_success "Backup created"

# Update Traefik config for v3
log_info "Updating Traefik configuration for v3..."
cat > infrastructure/docker/traefik/traefik.yml << 'EOF'
# Traefik v3 Static Configuration
global:
  checkNewVersion: true
  sendAnonymousUsage: false

api:
  dashboard: true
  insecure: false

entryPoints:
  web:
    address: ":80"
    http:
      redirections:
        entryPoint:
          to: websecure
          scheme: https
          permanent: true

  websecure:
    address: ":443"
    http:
      tls:
        certResolver: default
        domains:
          - main: "*.minder.local"
            sans:
              - "minder.local"

providers:
  docker:
    endpoint: "unix:///var/run/docker.sock"
    exposedByDefault: false
    network: docker_minder-network

  file:
    directory: /etc/traefik/dynamic
    watch: true

certificatesResolvers:
  default:
    acme:
      email: admin@minder.local
      storage: /letsencrypt/acme.json
      httpChallenge:
        entryPoint: web

log:
  level: INFO
  filePath: /var/log/traefik/traefik.log
  format: json

accessLog:
  filePath: /var/log/traefik/access.log
  format: json
  fields:
    headers:
      defaultMode: keep
      names:
        User-Agent: keep
        Authorization: keep

metrics:
  prometheus:
    entryPoint: websecure
    addEntryPointsLabels: true
    addServicesLabels: true
EOF
log_success "Traefik config updated to v3"

# Update Grafana provisioning for v11
log_info "Updating Grafana provisioning for v11..."
cat > infrastructure/docker/grafana/provisioning/dashboards/dashboard.yml << 'EOF'
apiVersion: 1

providers:
  - name: 'Minder Dashboards'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /etc/grafana/provisioning/dashboards
      foldersFromFilesStructure: true
EOF
log_success "Grafana provisioning updated"

# Update docker-compose.yml
log_info "Updating docker-compose.yml with new image versions..."
python3 << 'PYTHON_SCRIPT'
import re
import yaml

# Read current compose file
with open('infrastructure/docker/docker-compose.yml', 'r') as f:
    compose = yaml.safe_load(f)

# Version mappings for docker-compose
version_updates = {
    'traefik:v2.10': 'traefik:v3.1.6',
    'authelia/authelia:latest': 'authelia/authelia:4.38.7',
    'redis:7-alpine': 'redis:7.2-alpine',
    'ollama/ollama:latest': 'ollama/ollama:0.5.7',
    'qdrant/qdrant:v1.17.1': 'qdrant/qdrant:v1.18.0',
    'neo4j:5.15-community': 'neo4j:5.24-community',
    'influxdb:2.7.4': 'influxdb:2.8.3',
    'telegraf:1.38.3': 'telegraf:1.33.1',
    'prom/prometheus:v2.48.0': 'prom/prometheus:v2.55.1',
    'prom/alertmanager:v0.26.0': 'prom/alertmanager:v0.28.1',
    'grafana/grafana:10.2.2': 'grafana/grafana:11.4.0',
    'ghcr.io/open-webui/open-webui:main': 'ghcr.io/open-webui/open-webui:git-69d0a16',
    'prometheuscommunity/postgres-exporter:v0.12.0': 'prometheuscommunity/postgres-exporter:v0.15.0',
    'oliver006/redis_exporter:v1.55.0': 'oliver006/redis_exporter:v1.62.0',
    # Internal services
    'minder/api-gateway:latest': 'minder/api-gateway:1.0.0',
    'minder/plugin-registry:latest': 'minder/plugin-registry:1.0.0',
    'minder/rag-pipeline:latest': 'minder/rag-pipeline:1.0.0',
    'minder/model-management:latest': 'minder/model-management:1.0.0',
    'minder/marketplace:latest': 'minder/marketplace:1.0.0',
    'minder/plugin-state-manager:latest': 'minder/plugin-state-manager:2.1.0',
    'minder/tts-stt-service:latest': 'minder/tts-stt-service:2.1.0',
    'minder/model-fine-tuning:latest': 'minder/model-fine-tuning:2.1.0',
}

# Update service images
updated_services = []
for service_name, service_config in compose['services'].items():
    if 'image' in service_config:
        old_image = service_config['image']
        if old_image in version_updates:
            service_config['image'] = version_updates[old_image]
            updated_services.append(f"{service_name}: {old_image} → {version_updates[old_image]}")

# Write updated compose file
with open('infrastructure/docker/docker-compose.yml', 'w') as f:
    yaml.dump(compose, f, default_flow_style=False, sort_keys=False)

print("Updated services:")
for update in updated_services:
    print(f"  • {update}")
PYTHON_SCRIPT

log_success "docker-compose.yml updated"

log_info "================================================"
log_success "Docker Infrastructure Modernization Complete!"
log_info "================================================"
log_warning ""
log_warning "⚠️  CRITICAL NOTES:"
log_warning "1. PostgreSQL 16 → 17 upgrade FLAGGED for manual approval (data migration required)"
log_warning "2. Traefik v2 → v3 config refactored automatically"
log_warning "3. Grafana v10 → v11 config updated automatically"
log_warning ""
log_info "Next steps:"
log_info "1. Review changes: git diff infrastructure/docker/docker-compose.yml"
log_info "2. Test changes: docker compose -f infrastructure/docker/docker-compose.yml config"
log_info "3. Apply changes: ./setup.sh restart"
log_info "4. For PostgreSQL 17 upgrade, see: POSTGRESQL_MIGRATION.md"
