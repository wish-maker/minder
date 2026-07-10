# Monitoring Setup

Monitoring and observability for the Minder Platform.

> Deployment target is a Raspberry Pi 4 (RPi-4-01, ARM). This is a **development
> environment**; production hardening is not yet applied. All services run via
> `docker/compose/docker-compose.yml` (the hand-maintained source of truth) and are
> provisioned with `bash setup.sh`.

---

## Observability Stack

The platform ships a full observability stack. Only the services listed with a
**host port** are reachable from the Pi's network; everything else is internal-only.

| Component | Container | Image | Host Port | Role |
|---|---|---|---|---|
| Prometheus | `minder-prometheus` | `prom/prometheus:v3.13.0` | 9090 | Metrics collection + storage |
| Grafana | `minder-grafana` | `grafana/grafana:13.1` | 3000 | Dashboards / visualization |
| Alertmanager | `minder-alertmanager` | `prom/alertmanager:v0.33.1` | 9093 | Alert routing |
| Jaeger | `minder-jaeger` | `jaegertracing/all-in-one:1.76.0` | 16686 (UI) | Distributed tracing (all-in-one) |
| OTel Collector | `minder-otel-collector` | `otel/opentelemetry-collector:0.156.0` | 14317 / 14318 / 18888 | OpenTelemetry pipeline |
| InfluxDB | `minder-influxdb` | `influxdb:3.10.1-core` | 8086 | Time-series data |
| Telegraf | `minder-telegraf` | `telegraf:1.39.1` | — | Metrics collection agent |

### Exporters (all internal, scraped by Prometheus)

| Exporter | Image | Internal Port |
|---|---|---|
| postgres-exporter | `v0.20.1` | 9187 |
| redis-exporter | `v1.86.0` | 9121 |
| rabbitmq-exporter | `v1.0.0-RC9` | 9090 (internal) |
| node-exporter | `v1.11.1` | 9100 |
| cadvisor | `gcr.io/cadvisor/cadvisor:v0.55.1` | 8080 |
| blackbox-exporter | `v0.28.0` | 9115 |

> **OTel Collector ports** are remapped (14317/14318/18888 instead of the default
> 4317/4318) to avoid a conflict with Jaeger's own OTLP ports on the all-in-one image.

---

## Healthcheck Status (Important)

28 of 31 containers define a Docker healthcheck. **Three do not, by design** — the base
images lack the tooling (e.g. `nc`) a healthcheck would need:

- `minder-otel-collector`
- `minder-redis-exporter`
- `minder-rabbitmq-exporter`

These show as **"no healthcheck"** in `docker ps`, which is **not the same as
"unhealthy"**. Any older note claiming redis-exporter or otel-collector is "unhealthy"
is stale — they are simply running without a healthcheck.

---

## Quick Start

The full stack comes up with the rest of the platform:

```bash
bash setup.sh start
```

To bring up only the monitoring services:

```bash
docker compose --file docker/compose/docker-compose.yml up -d \
  prometheus grafana alertmanager jaeger otel-collector influxdb telegraf \
  postgres-exporter redis-exporter rabbitmq-exporter node-exporter cadvisor blackbox-exporter
```

### Verify

```bash
# Containers running
docker ps | grep -E "prometheus|grafana|alertmanager|jaeger|otel-collector|influxdb|telegraf"

# Prometheus targets
curl http://localhost:9090/api/v1/targets

# Prometheus / Grafana / Alertmanager health
curl http://localhost:9090/-/healthy
curl http://localhost:3000/api/health
curl http://localhost:9093/-/healthy

# Jaeger UI
# http://localhost:16686
```

### Grafana access

- URL: `http://localhost:3000`
- Default credentials: `admin` / `admin` (change on first login)

Grafana is also routed through Traefik with an `authelia-forwardauth` middleware.
Authelia is currently **disabled** (commented out in compose), so that forward-auth is
**not enforced** today. Direct access on port 3000 works as normal.

The Prometheus datasource points at `http://minder-prometheus:9090` (internal Docker DNS
name). Dashboards live in `docker/services/grafana/dashboards/`.

---

## Instrumentation (OpenTelemetry)

Application services are instrumented with OpenTelemetry and export to the
**OTel Collector** at `minder-otel-collector:14317` (OTLP gRPC). The collector fans out
to Jaeger (traces) and Prometheus/metrics as configured. Prometheus additionally scrapes
the app services and exporters directly.

```
services ──OTLP──▶ otel-collector (:14317 gRPC / :14318 HTTP)
                       │
                       ├──▶ Jaeger (traces, UI :16686)
                       └──▶ metrics pipeline (:18888)

Prometheus (:9090) ──scrape──▶ app services + exporters
```

---

## Prometheus Configuration

Config lives at `docker/services/prometheus/prometheus.yml`. Scrape the core API services
by their container names and internal ports:

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'minder-api-gateway'
    static_configs:
      - targets: ['minder-api-gateway:8000']

  - job_name: 'minder-plugin-registry'
    static_configs:
      - targets: ['minder-plugin-registry:8001']

  - job_name: 'minder-marketplace'
    static_configs:
      - targets: ['minder-marketplace:8002']

  - job_name: 'minder-plugin-state-manager'
    static_configs:
      - targets: ['minder-plugin-state-manager:8003']

  - job_name: 'minder-rag-pipeline'
    static_configs:
      - targets: ['minder-rag-pipeline:8004']

  - job_name: 'minder-model-management'
    static_configs:
      - targets: ['minder-model-management:8005']

  - job_name: 'minder-tts-stt'
    static_configs:
      - targets: ['minder-tts-stt:8006']

  - job_name: 'minder-graph-rag'
    static_configs:
      - targets: ['minder-graph-rag:8008']

  # Exporters
  - job_name: 'postgres'
    static_configs:
      - targets: ['minder-postgres-exporter:9187']

  - job_name: 'redis'
    static_configs:
      - targets: ['minder-redis-exporter:9121']

  - job_name: 'rabbitmq'
    static_configs:
      - targets: ['minder-rabbitmq-exporter:9090']

  - job_name: 'node'
    static_configs:
      - targets: ['minder-node-exporter:9100']

  - job_name: 'cadvisor'
    static_configs:
      - targets: ['minder-cadvisor:8080']

  - job_name: 'blackbox'
    static_configs:
      - targets: ['minder-blackbox-exporter:9115']
```

---

## Available Dashboards

Dashboards are provisioned from `docker/services/grafana/dashboards/`. They cover:

- **Minder Overview** — service health, request metrics, error rates, resource usage
- **API Gateway** — HTTP request count/latency, health, JWT auth activity
- **PostgreSQL** — database size, connection counts, query performance
- **Redis** — memory usage, connections, cache hit rate

---

## Alerting

### Prometheus alert rules

Alert rules live under `docker/services/prometheus/` (e.g. `alerts.yml`):

```yaml
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
        expr: container_memory_usage_bytes / container_spec_memory_limit_bytes > 0.9
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage"
          description: "Container {{ $labels.name }} is using >90% of its memory limit"
```

### Alertmanager

Config lives at `docker/services/alertmanager/alertmanager.yml`. Email/SMTP routing is a
placeholder — fill in real values before relying on notifications:

```yaml
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
      - to: 'admin@example.com'
        from: 'alerts@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'alerts@example.com'
        auth_password: 'CHANGEME'
```

---

## Monitoring Best Practices

- Review Grafana dashboards regularly; watch trends and anomalies.
- Set alert thresholds appropriate for a single Raspberry Pi 4 (memory and CPU are the
  limiting factors — see `hardware-optimization.md`).
- Test alert delivery after changing Alertmanager receivers.

### Centralized logging (future / not built in)

There is currently **no** centralized log aggregation (no ELK/Loki). Logs are the
per-container Docker logs. A log-aggregation layer (Loki, etc.) is a possible future
addition, not something shipped today.

---

## Handy Scripts

```bash
# Query the "up" metric across all targets
curl -s 'http://localhost:9090/api/v1/query?query=up' | jq '.'

# Live container resource usage
docker stats --no-stream | grep minder

# Tail a service's logs
docker logs minder-<service> --tail 100 -f
```

---

## Related Documentation

- [Production Deployment Guide](production.md)
- [Hardware Optimization](hardware-optimization.md)
- [Backup Strategy](infrastructure-backup-strategy.md)

---

## Getting Help

- Prometheus docs: https://prometheus.io/docs/
- Grafana docs: https://grafana.com/docs/
- Jaeger docs: https://www.jaegertracing.io/docs/
- OpenTelemetry Collector docs: https://opentelemetry.io/docs/collector/

---

**Last Updated:** 2026-07-10
