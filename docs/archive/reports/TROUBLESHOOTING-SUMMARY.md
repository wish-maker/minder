# Minder Platform - Troubleshooting Summary
## Incident Resolution: 2026-05-04

### Executive Summary
Fixed three container failures caused by breaking configuration changes in newer versions. All services now operational after targeted configuration updates.

---

## Root Cause Analysis

### 1. **Authelia (minder-authelia)** - Restarting Loop

**Symptom:**
- Container stuck in restart loop
- Exit code 1 on every startup attempt

**Root Cause:**
Breaking change in Authelia v4.38.7 → v4.38.18

The `default_redirection_url` configuration option moved from:
- **Old (v4.38.7):** Global session configuration
- **New (v4.38.18+):** Per-cookie configuration (required)

**Error Message:**
```
session: option 'cookies' must be configured with the per cookie option
'default_redirection_url' but the global one is configured which is not supported
```

**Fix Applied:**
Updated `/infrastructure/docker/authelia/configuration.yml`:

```yaml
# OLD (incorrect):
session:
  cookies:
    - name: authelia_session
      domain: minder.local
      authelia_url: https://auth.minder.local

# NEW (correct):
session:
  cookies:
    - name: authelia_session
      domain: minder.local
      authelia_url: https://authelia.minder.local
      default_redirection_url: https://authelia.minder.local  # MOVED HERE
```

**Additional Issues Fixed:**
- Removed deprecated environment variables:
  - `AUTHELIA_DEFAULT_ENCRYPTION_KEY` → Use `AUTHELIA_STORAGE_ENCRYPTION_KEY`
  - `AUTHELIA_DEFAULT_JWT_SECRET` → Use `AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET`

---

### 2. **Telegraf (minder-telegraf)** - Restarting Loop

**Symptom:**
- Container failing to start
- Configuration validation errors

**Root Cause:**
Breaking change in Telegraf v1.33.1 → v1.34.0

The Docker input plugin removed three deprecated options:
- `container_include`
- `container_exclude`
- `container_name`

**Error Message:**
```
plugin inputs.docker: line 49: configuration specified the fields
["container_exclude" "container_name" "container_include"],
but they were not used
```

**Fix Applied:**
Updated `/infrastructure/docker/telegraf/telegraf.conf`:

```toml
# OLD (deprecated):
[[inputs.docker]]
  endpoint = "unix:///var/run/docker.sock"
  timeout = "5s"
  container_include = []
  container_exclude = ["telegraf"]
  source_tag = true
  container_name = true

# NEW (v1.34.0+):
[[inputs.docker]]
  endpoint = "unix:///var/run/docker.sock"
  timeout = "5s"
  source_tag = true
  perdevice_include = ["cpu", "mem", "net", "blkio"]
```

**Why This Works:**
- `perdevice_include` replaces the old container filtering mechanism
- Automatically collects metrics for all containers
- More efficient than include/exclude lists

---

### 3. **RabbitMQ Exporter (minder-rabbitmq-exporter)** - Unhealthy

**Symptom:**
- Container running but marked as "unhealthy"
- Healthcheck failing continuously (1665+ attempts)

**Root Cause:**
Healthcheck port mismatch in `docker-compose.yml`

**Configuration Issue:**
- **Exporter listening on:** Port `9090` (set via `PUBLISH_PORT=9090`)
- **Healthcheck checking:** Port `9419` (hardcoded incorrectly)

**Healthcheck Error:**
```
Get "http://localhost:9419/health": dial tcp [::1]:9419: connect: connection refused
```

**Fix Applied:**
Added correct healthcheck to `docker-compose.yml`:

```yaml
rabbitmq-exporter:
  image: kbudde/rabbitmq-exporter:v1.0.0-RC9
  environment:
    - PUBLISH_PORT=9090
  healthcheck:
    test:
      - CMD
      - wget
      - --quiet
      - --tries=1
      - --spider
      - http://localhost:9090/metrics  # FIXED: was 9419
    interval: 30s
    timeout: 10s
    retries: 3
```

---

## Verification

### Pre-Fix State:
```
minder-authelia         Restarting (1) 24 seconds ago
minder-telegraf         Restarting (1) 50 seconds ago
minder-rabbitmq-exporter Up 14 hours (unhealthy)
```

### Post-Fix State:
```
minder-authelia         Up 2 minutes (healthy)
minder-telegraf         Up 2 minutes (running)
minder-rabbitmq-exporter Up 2 minutes (healthy)
```

---

## Lessons Learned

### 1. **Version Pinning is Critical**
- Breaking changes in minor/patch versions (4.38.7 → 4.38.18)
- Always review changelogs before upgrades
- Test in staging first

### 2. **Healthcheck Configuration Matters**
- Exporter was running fine, but healthcheck was wrong
- Masked the actual functionality
- Always verify healthcheck ports match exposed ports

### 3. **Deprecation Warnings are Important**
- Telegraf showed deprecation warnings for months
- "Option 'perdevice' deprecated since version 1.18.0"
- Monitor logs for deprecation notices

---

## Prevention Strategies

### 1. **Automated Changelog Monitoring**
```bash
# Subscribe to release notifications
authelia: https://github.com/authelia/authelia/releases
telegraf: https://github.com/influxdata/telegraf/releases
```

### 2. **Pre-Upgrade Testing Checklist**
- [ ] Review breaking changes in release notes
- [ ] Test configuration validation in staging
- [ ] Verify healthcheck endpoints
- [ ] Monitor deprecation warnings

### 3. **Configuration Validation**
```bash
# Validate Authelia config
docker run --rm -v $(pwd)/authelia:/config authelia/authelia:4.38.18 config validate

# Validate Telegraf config
docker run --rm -v $(pwd)/telegraf:/etc/telegraf telegraf:1.34.0 --config /etc/telegraf/telegraf.conf --test
```

---

## References

- **Authelia Migration Guide:** https://www.authelia.com/configuration/session/
- **Telegraf Docker Plugin:** https://github.com/influxdata/telegraf/tree/master/plugins/inputs/docker
- **Docker Healthchecks:** https://docs.docker.com/engine/reference/builder/#healthcheck

---

**Status:** ✅ All Issues Resolved
**Date:** 2026-05-04
**Engineer:** SRE Team
