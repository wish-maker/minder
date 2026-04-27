# 📊 Monitoring Setup

Complete monitoring setup for Prometheus and Grafana.

---

## 🎯 Monitoring Overview

The Minder Platform includes a comprehensive monitoring stack:

- **Prometheus** - Metrics collection and storage
- **Grafana** - Visualization and dashboards
- **Custom Exporters** - Service-specific metrics

---

## 🚀 Quick Start

### 1. Start Monitoring Stack

```bash
cd /root/minder/infrastructure/docker
docker compose up -d prometheus grafana telegraf postgres-exporter redis-exporter
```

### 2. Verify Services

```bash
# Check containers running
docker ps | grep -E "prometheus|grafana|telegraf|postgres-exporter|redis-exporter"

# Check Prometheus targets
curl http://localhost:9090/api/v1/targets

# Access Grafana
# URL: http://localhost:3000
# Credentials: admin/admin
```

### 3. Configure Datasource in Grafana

1. Login to Grafana
2. Go to **Configuration** → **Data Sources**
3. Click **Add data source**
4. Select **Prometheus**
5. URL: `http://minder-prometheus:9090`
6. Click **Save & test**

---

## 📊 Available Dashboards

### Default Dashboard

**[Minder Overview](http://localhost:3000/dashboards)**

- Service health status
- Request metrics
- Error rates
- Resource usage

### Service Dashboards

1. **API Gateway**
   - HTTP requests (count, latency)
   - Health status
   - JWT authentication metrics

2. **Plugin Registry**
   - Plugin count
   - Plugin health
   - Load metrics

3. **PostgreSQL**
   - Database size
   - Connection counts
   - Query performance

4. **Redis**
   - Memory usage
   - Connection count
   - Cache hit rate

---

## 🔧 Prometheus Configuration

### Default Configuration

```yaml
# infrastructure/docker/prometheus.yml

global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # API Gateway
  - job_name: 'minder-api-gateway'
    static_configs:
      - targets: ['minder-api-gateway:8000']

  # Plugin Registry
  - job_name: 'minder-plugin-registry'
    static_configs:
      - targets: ['minder-plugin-registry:8001']

  # RAG Pipeline
  - job_name: 'minder-rag-pipeline'
    static_configs:
      - targets: ['minder-rag-pipeline:8004']

  # Model Management
  - job_name: 'minder-model-management'
    static_configs:
      - targets: ['minder-model-management:8005']

  # PostgreSQL Exporter
  - job_name: 'postgres'
    static_configs:
      - targets: ['minder-postgres-exporter:9187']

  # Redis Exporter
  - job_name: 'redis'
    static_configs:
      - targets: ['minder-redis-exporter:9121']
```

---

## 📈 Metrics Collection

### HTTP Metrics

```python
from prometheus_client import Counter, Histogram, Summary

# Request counter
http_requests_total = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

# Request duration
http_request_duration = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration',
    ['method', 'endpoint']
)

# Request summary
http_request_summary = Summary(
    'http_request_summary_seconds',
    'HTTP request summary'
)
```

### Database Metrics

```python
from prometheus_client import Gauge

# Connection count
postgres_connections = Gauge(
    'postgres_connections',
    'PostgreSQL connections'
)

postgres_active_connections = Gauge(
    'postgres_active_connections',
    'Active PostgreSQL connections'
)

postgres_connection_count = Gauge(
    'postgres_connection_count',
    'Total PostgreSQL connections'
)
```

### Plugin Metrics

```python
# Plugin health
plugins_health_status = Gauge(
    'plugins_health_status',
    'Plugin health status (0=unhealthy, 1=healthy)',
    ['plugin_name']
)

# Data collection metrics
data_collection_count = Counter(
    'data_collection_total',
    'Total data collection events',
    ['plugin_name']
)

data_collection_duration = Histogram(
    'data_collection_duration_seconds',
    'Data collection duration',
    ['plugin_name']
)
```

---

## 🔔 Alerting Setup

### Create Alert Rules

```yaml
# infrastructure/docker/alerts.yml

groups:
  - name: minder_alerts
    interval: 30s
    rules:
      - alert: ServiceDown
        expr: up{job="minder-api-gateway"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "API Gateway is down"
          description: "API Gateway has been down for more than 1 minute"

      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} requests/sec"

      - alert: HighMemoryUsage
        expr: docker_container_memory_usage_bytes / docker_container_memory_limit_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Container {{ $labels.name }} is using {{ $value }}% of memory"
```

### Configure Alertmanager

```yaml
# infrastructure/docker/alertmanager.yml

global:
  resolve_timeout: 5m

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'

receivers:
  - name: 'default'
    email_configs:
      - to: 'admin@minder.example.com'
        from: 'alerts@minder.example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alerts@minder.example.com'
        auth_password: 'your-password'
```

---

## 🔍 Monitoring Best Practices

### 1. Regular Monitoring

- Check Grafana dashboards daily
- Review Prometheus alerts weekly
- Monitor trends and anomalies

### 2. Alert Configuration

- Set appropriate thresholds
- Test alerts regularly
- Review alert effectiveness

### 3. Log Monitoring

- Centralized logging (optional)
- Log aggregation (ELK stack or Loki)
- Log analysis and alerts

### 4. Performance Monitoring

- Track response times
- Monitor resource usage
- Analyze database performance

---

## 🛠️ Monitoring Scripts

### Health Check Script

```bash
#!/bin/bash
# scripts/monitoring/health_check.sh

SERVICES=(
    "minder-api-gateway:8000/health"
    "minder-plugin-registry:8001/health"
    "minder-postgres:5432"
    "minder-redis:6379"
)

for service in "${SERVICES[@]}"; do
    HOST=${service%:*}
    PORT=${service#*:}

    if nc -z $HOST $PORT; then
        echo "✅ $HOST:$PORT is healthy"
    else
        echo "❌ $HOST:$PORT is down"
        # Send notification (Slack, email, etc.)
    fi
done
```

### Metrics Collection Script

```bash
#!/bin/bash
# scripts/monitoring/collect_metrics.sh

# Collect Prometheus metrics
curl -s http://localhost:9090/api/v1/query?query=up | jq '.'

# Collect service status
docker stats --no-stream | grep minder

# Collect database stats
docker exec minder-postgres psql -U minder -d minder -c "SELECT count(*) FROM plugins;"
```

---

## 📚 Related Documentation

- **[Deployment Guide](DEPLOYMENT_GUIDE.md)** - Complete deployment guide
- **[API Reference](../api/README.md)** - API documentation
- **[Common Issues](../troubleshooting/common-issues.md)** - Troubleshooting

---

## 🤝 Getting Help

- **Prometheus Documentation:** https://prometheus.io/docs/
- **Grafana Documentation:** https://grafana.com/docs/
- **Grafana Labs:** https://grafana.com/oss/monitoring/
- **GitHub Issues:** https://github.com/wish-maker/minder/issues

---

**Last Updated:** 2026-04-19
