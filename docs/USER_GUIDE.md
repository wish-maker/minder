# Minder User Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Plugin System](#plugin-system)
4. [API Usage](#api-usage)
5. [Monitoring](#monitoring)
6. [Troubleshooting](#troubleshooting)

## Introduction

Minder is a **Modular RAG (Retrieval-Augmented Generation) Platform** with hot-swappable plugins for data collection, analysis, and AI-powered insights.

### Key Features
- 🔌 **Modular Plugin Architecture**: Easily add/remove functionality
- 🛡️ **Enterprise Security**: JWT auth, rate limiting, input sanitization
- 📊 **Comprehensive Monitoring**: Real-time metrics and performance tracking
- 🚀 **Production Ready**: Auto-scaling, backups, rollback capabilities
- 🔍 **Multi-Source Data**: Weather, crypto, news, TEFAS, and more

### What Can Minder Do?
- **Data Collection**: Automatically gather data from multiple sources
- **Analysis**: Process and analyze collected data
- **AI Training**: Train ML models on your data
- **Knowledge Graphing**: Build searchable knowledge bases
- **Correlation Discovery**: Find hidden patterns across data sources

## Getting Started

### Installation

#### Option 1: Quick Start (Recommended)
```bash
# Clone repository
git clone https://github.com/wish-maker/minder.git
cd minder

# Run setup script
bash scripts/setup_environment.sh

# Start application
docker compose up -d

# Verify installation
curl http://localhost:8000/health
```

#### Option 2: Manual Installation
```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
nano .env  # Edit configuration

# Start databases
docker compose up -d postgres influxdb qdrant redis

# Run application
python3 -m api.main
```

### First Steps

#### 1. Check System Health
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "system": {
    "status": "running",
    "plugins": {"total": 5, "ready": 5}
  }
}
```

#### 2. List Available Plugins
```bash
curl http://localhost:8000/plugins
```

#### 3. Run a Plugin Pipeline
```bash
# Run crypto plugin pipeline
curl -X POST http://localhost:8000/plugins/crypto/pipeline \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline": ["collect", "analyze", "train", "index"]
  }'
```

## Plugin System

### Available Plugins

#### 1. Weather Plugin
**Capabilities**: Weather data collection, forecast analysis, seasonal patterns

```bash
# Collect weather data
curl -X POST http://localhost:8000/plugins/weather/collect_data

# Get analysis
curl -X POST http://localhost:8000/plugins/weather/analyze
```

#### 2. Crypto Plugin
**Capabilities**: Cryptocurrency price tracking, volume analysis, sentiment analysis

```bash
# Collect crypto prices
curl -X POST http://localhost:8000/plugins/crypto/collect_data

# Get current prices
curl http://localhost:8000/plugins/crypto/query?query=BTC+price
```

#### 3. News Plugin
**Capabilities**: News aggregation, sentiment analysis, trend detection

```bash
# Collect latest news
curl -X POST http://localhost:8000/plugins/news/collect_data

# Analyze sentiment
curl -X POST http://localhost:8000/plugins/news/analyze
```

#### 4. Network Plugin
**Capabilities**: Network monitoring, traffic analysis, security detection

```bash
# Monitor network
curl -X POST http://localhost:8000/plugins/network/collect_data

# Get network stats
curl http://localhost:8000/plugins/network/analyze
```

#### 5. TEFAS Plugin
**Capabilities**: Turkish investment fund analysis, performance tracking

```bash
# Collect fund data
curl -X POST http://localhost:8000/plugins/tefas/collect_data

# Get fund performance
curl http://localhost:8000/plugins/tefas/query?query=fund+performance
```

### Installing Custom Plugins

#### From GitHub
```bash
curl -X POST http://localhost:8000/plugins/install \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/username/minder-plugin"
  }'
```

#### Local Installation
```bash
# Copy plugin to plugins directory
cp -r my-plugin /root/minder/plugins/

# Restart Minder
docker compose restart api
```

## API Usage

### Authentication

#### Get API Token
```bash
# Login
TOKEN=$(curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "your_password"
  }' | jq -r '.access_token')

# Use token
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/plugins
```

### Core Endpoints

#### Plugin Management
```bash
# List all plugins
GET /plugins

# Get plugin details
GET /plugins/{plugin_name}

# Run plugin operation
POST /plugins/{plugin_name}/{operation}

# Install new plugin
POST /plugins/install
```

#### System Monitoring
```bash
# System status
GET /system/status

# Health check
GET /health

# Metrics
GET /metrics
```

#### Data Operations
```bash
# Query data
POST /plugins/{plugin_name}/query

# Discover correlations
GET /correlations

# Get knowledge graph
GET /knowledge_graph
```

### Example Workflows

#### Collect and Analyze Crypto Data
```bash
# 1. Collect data
curl -X POST http://localhost:8000/plugins/crypto/collect_data

# 2. Analyze trends
curl -X POST http://localhost:8000/plugins/crypto/analyze

# 3. Train model
curl -X POST http://localhost:8000/plugins/crypto/train_ai

# 4. Query results
curl -X POST http://localhost:8000/plugins/crypto/query \
  -H "Content-Type: application/json" \
  -d '{"query": "BTC price trends"}'
```

#### Discover Cross-Domain Correlations
```bash
# Find correlations between crypto and news
curl -X POST http://localhost:8000/correlations/discover \
  -H "Content-Type: application/json" \
  -d '{
    "plugin_a": "crypto",
    "plugin_b": "news"
  }'
```

## Monitoring

### Using the Monitoring CLI

#### System Metrics
```bash
python3 scripts/monitoring_cli.py system
```

Output:
```
CPU Usage:
  Current: 25.3%
  Average: 28.1%
  Status: ok

Memory Usage:
  Current: 45.2%
  Available: 4908 MB
  Status: ok
```

#### API Performance
```bash
python3 scripts/monitoring_cli.py api
```

Output:
```
Total Requests: 1234
Average Response Time: 250ms
P95 Response Time: 800ms
Error Rate: 0.5%
```

#### Plugin Metrics
```bash
python3 scripts/monitoring_cli.py plugins
```

Output:
```
WEATHER:
  Total Operations: 45
  Success Rate: 100.0%
  Avg Duration: 1200ms

CRYPTO:
  Total Operations: 89
  Success Rate: 98.9%
  Avg Duration: 800ms
```

### Real-Time Monitoring

#### Health Dashboard
```bash
# Continuous health monitoring
watch -n 5 'curl -s http://localhost:8000/health | jq .'
```

#### Plugin Status
```bash
# Monitor plugin status
watch -n 10 'curl -s http://localhost:8000/plugins | jq .'
```

## Troubleshooting

### Common Issues

#### Issue: Plugin Won't Load
**Symptoms**: Plugin shows as "error" status

**Solutions**:
```bash
# Check plugin logs
docker logs minder-api | grep plugin_name

# Verify plugin files
ls -la plugins/plugin_name/

# Check dependencies
cat plugins/plugin_name/plugin.yml
```

#### Issue: High CPU Usage
**Symptoms**: System slow, CPU > 80%

**Solutions**:
```bash
# Check current metrics
python3 scripts/monitoring_cli.py system

# Restart containers
docker compose restart

# Scale down if needed
# Edit docker-compose.yml
# Reduce WORKERS environment variable
```

#### Issue: Database Connection Failed
**Symptoms**: "Database connection error" in logs

**Solutions**:
```bash
# Check database status
docker compose ps

# Restart database
docker compose restart postgres

# Verify credentials
grep POSTGRES .env
```

### Getting Help

#### Logs
```bash
# Application logs
docker logs -f minder-api

# Database logs
docker logs -f postgres

# All logs
docker compose logs -f
```

#### Diagnostic Information
```bash
# Full system status
curl http://localhost:8000/system/status

# Environment info
docker compose config

# Resource usage
docker stats
```

#### Support Resources
- **Documentation**: See `/docs` directory
- **API Reference**: http://localhost:8000/docs
- **GitHub Issues**: https://github.com/wish-maker/minder/issues
- **Troubleshooting Guide**: See `/docs/TROUBLESHOOTING.md`

## Best Practices

### Performance
1. **Use Plugin Pipelines**: Combine multiple operations in one call
2. **Enable Caching**: Configure Redis for frequently accessed data
3. **Monitor Resources**: Use monitoring CLI to track performance
4. **Schedule Operations**: Run data collection during off-peak hours

### Security
1. **Use Strong Passwords**: Generate secure JWT secrets and database passwords
2. **Enable Rate Limiting**: Prevent abuse with rate limits
3. **Regular Updates**: Keep dependencies updated
4. **Backup Regularly**: Automated daily backups recommended

### Operations
1. **Monitor Health**: Check `/health` endpoint regularly
2. **Review Logs**: Check for errors and warnings
3. **Test Backups**: Verify backup restoration procedure
4. **Plan Scaling**: Monitor resource usage and plan capacity

## Advanced Usage

### Custom Plugin Development
See `/docs/development/plugin-development.md`

### API Integration
See `/docs/development/api-integration.md`

### Production Deployment
See `/deployment/production-deployment.md`

---

**Last Updated**: 2026-04-18
**Version**: 1.0.0
