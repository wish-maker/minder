# InfluxDB + Telegraf Setup Guide

## Overview

Minder platform now supports time-series monitoring using:
- **InfluxDB 2.x**: Time-series database for metrics storage
- **Telegraf**: Metrics collection agent (200+ input plugins)
- **Grafana**: Visualization dashboards with InfluxDB datasource

## Quick Start

### 1. Start Services

```bash
cd /root/minder/infrastructure/docker

# Start core services + InfluxDB + Telegraf + Grafana
docker-compose --profile monitoring up -d influxdb telegraf grafana

# Or start everything
docker-compose --profile monitoring up -d
```

### 2. Access Services

- **InfluxDB UI**: http://localhost:8086
  - Username: `admin` (or from INFLUXDB_ADMIN_USERNAME env)
  - Password: From `.env` file (INFLUXDB_ADMIN_PASSWORD)
  - Token: From `.env` file (INFLUXDB_TOKEN)

- **Grafana**: http://localhost:3000
  - Username: `admin`
  - Password: From `.env` file (GRAFANA_ADMIN_PASSWORD)

- **Telegraf**: No UI (runs in background)

### 3. Verify Setup

```bash
# Check InfluxDB
curl http://localhost:8086/health

# Check Telegraf logs
docker logs minder-telegraf --tail 50

# Check Grafana
curl http://localhost:3000/api/health
```

## Configuration

### Environment Variables (.env)

```bash
# InfluxDB
INFLUXDB_ADMIN_USERNAME=admin
INFLUXDB_ADMIN_PASSWORD=secure_password_here
INFLUXDB_INIT_ORG=minder
INFLUXDB_INIT_BUCKET=minder-metrics
INFLUXDB_TOKEN=your_influxdb_auth_token_here_change_me

# Grafana
GRAFANA_ADMIN_PASSWORD=admin
```

### Telegraf Configuration

Located at: `infrastructure/docker/telegraf/telegraf.conf`

Key inputs:
- `inputs.cpu`: CPU metrics
- `inputs.mem`: Memory metrics
- `inputs.disk`: Disk usage
- `inputs.net`: Network interface stats
- `inputs.postgresql`: PostgreSQL metrics
- `inputs.redis`: Redis metrics
- `inputs.http`: Minder plugin registry metrics

## Plugin Integration

### Network Plugin (Dual-Write)

The network plugin now writes to both PostgreSQL and InfluxDB:

```python
# Plugin configuration
{
    "database": {
        "host": "postgres",
        "port": 5432,
        "database": "minder",
        "user": "minder",
        "password": "your_password"
    },
    "influxdb": {
        "enabled": true,
        "url": "http://influxdb:8086",
        "token": "your_token",
        "org": "minder",
        "bucket": "minder-metrics"
    },
    "network": {
        "interfaces": ["eth0", "wlan0"],
        "collection_interval": 60
    }
}
```

### Querying InfluxDB

Using Flux query language:

```flux
// Average CPU usage over last hour
from(bucket: "minder-metrics")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "network_metrics")
  |> filter(fn: (r) => r.metric_name == "cpu_usage_percent")
  |> aggregateWindow(every: 5m, fn: mean, createEmpty: false)
  |> yield(name: "avg_cpu")
```

## Grafana Dashboards

### Create Dashboard

1. Login to Grafana (http://localhost:3000)
2. Go to Dashboards → New → Import
3. Select InfluxDB datasource
4. Add panels with Flux queries

### Example Panel Queries

**CPU Usage:**
```flux
from(bucket: "minder-metrics")
  |> range(start: $from)
  |> filter(fn: (r) => r._measurement == "network_metrics")
  |> filter(fn: (r) => r.metric_name == "cpu_usage_percent")
  |> aggregateWindow(every: 1m, fn: mean)
```

**Memory Usage:**
```flux
from(bucket: "minder-metrics")
  |> range(start: $from)
  |> filter(fn: (r) => r._measurement == "network_metrics")
  |> filter(fn: (r) => r.metric_name == "memory_usage_percent")
  |> aggregateWindow(every: 1m, fn: mean)
```

## Troubleshooting

### InfluxDB Not Starting

```bash
# Check logs
docker logs minder-influxdb --tail 100

# Check port conflicts
netstat -tlnp | grep 8086

# Reinitialize InfluxDB
docker-compose down -v
docker-compose up -d influxdb
```

### Telegraf Not Sending Data

```bash
# Check Telegraf logs
docker logs minder-telegraf --tail 100

# Verify configuration
docker exec minder-telegraf telegraf --config /etc/telegraf/telegraf.conf --test

# Check InfluxDB bucket exists
influx bucket list --org minder
```

### Grafana Datasource Not Working

1. Verify datasource settings in Grafana UI
2. Test connection: Configuration → Data Sources → InfluxDB → Test
3. Check token has correct permissions

## Maintenance

### Backup InfluxDB Data

```bash
# Backup to file
docker exec minder-influxdb influx backup /tmp/backup --bucket minder-metrics

# Copy to host
docker cp minder-influxdb:/tmp/backup ./influxdb-backup
```

### Retention Policies

Default: 30 days for `minder-metrics` bucket

To create long-term storage:

```bash
# Create 1-year retention bucket
influx bucket create \
  --org minder \
  --name minder-metrics-1y \
  --retention 365d
```

### Clean Old Data

```bash
# Delete data older than 30 days
influx delete \
  --org minder \
  --bucket minder-metrics \
  --start 1970-01-01T00:00:00Z \
  --stop $(date -d '30 days ago' +%Y-%m-%dT%H:%M:%SZ)
```

## Next Steps

1. **Custom Dashboards**: Create Grafana dashboards for your use case
2. **Alerting**: Configure Grafana alerts on metric thresholds
3. **Additional Plugins**: Add InfluxDB support to other plugins
4. **Downsampling**: Set up task to downsample old data

## Resources

- [InfluxDB 2.x Documentation](https://docs.influxdata.com/influxdb/v2/)
- [Telegraf Documentation](https://docs.influxdata.com/telegraf/v1/)
- [Grafana InfluxDB Plugin](https://grafana.com/docs/grafana/latest/datasources/influxdb/)
- [Flux Query Language](https://docs.influxdata.com/flux/v0/)
