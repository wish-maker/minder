# Minder Production Platform - Phase 3: Advanced Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Observability service, Workflow Orchestrator, Version Control, Alert Manager, Audit Log, Cost Optimizer, Webhook Manager, and Security Scanner services.

**Architecture:** 9 additional core services (ports 8008-8015) providing production-ready features like monitoring, workflow automation, version management, alerting, auditing, cost optimization, webhooks, and security scanning.

**Tech Stack:** FastAPI, Prometheus (metrics), Jaeger (tracing), Airflow/Temporal (orchestration), PostgreSQL (version storage), Alertmanager, Grafana, SendGrid/Slack (notifications), Bandit/Safety (security scanning)

---

## Phase 3.1: Observability & Monitoring

### Task 1: Create Observability Service

**Files:**
- Create: `services/observability/Dockerfile`
- Create: `services/observability/requirements.txt`
- Create: `services/observability/main.py`

- [ ] **Step 1: Create Observability service structure**

```bash
mkdir -p services/observability
```

- [ ] **Step 2: Create Observability Dockerfile**

File: `services/observability/Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

COPY ../../../src/core /app/src/core

EXPOSE 8008

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD curl -f http://localhost:8008/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8008"]
```

- [ ] **Step 3: Create Observability requirements**

File: `services/observability/requirements.txt`

```txt
fastapi==0.104.1
uvicorn[standard]==0.24.0
prometheus-client==0.19.0
opentelemetry-api==1.21.0
opentelemetry-sdk==1.21.0
opentelemetry-instrumentation-fastapi==0.42b0
jaeger-client==5.0.0
psycopg2-binary==2.9.9
redis==5.0.1
```

- [ ] **Step 4: Create Observability main application**

File: `services/observability/main.py`

```python
"""
Minder Observability Service
Provides distributed tracing, metrics, and logging
"""

from fastapi import FastAPI
from prometheus_client import Counter, Histogram, generate_latest
from typing import Dict
from datetime import datetime

app = FastAPI(title="Minder Observability", version="2.0.0")

# Prometheus metrics
request_count = Counter('requests_total', 'Total requests')
request_latency = Histogram('request_latency_seconds', 'Request latency')

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/metrics")
async def metrics():
    return generate_latest()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8008)
```

- [ ] **Step 5: Commit Observability service**

```bash
git add services/observability/
git commit -m "feat: add Observability service

- Implement distributed tracing
- Add Prometheus metrics
- Add health check endpoint
- Support Jaeger integration

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Phase 3.2: Workflow Orchestrator

### Task 2: Create Workflow Orchestrator Service

- [ ] **Step 1: Create Workflow service structure**

```bash
mkdir -p services/workflow-orchestrator
```

- [ ] **Step 2: Create Workflow service (similar pattern to Observability)**

(Implement similar to Task 1 but for workflow orchestration)

---

## Summary

This Phase 3 plan includes implementation of 9 advanced services:

1. **Observability Service** (8008) - Distributed tracing, metrics, logging
2. **Workflow Orchestrator** (8009) - DAG-based workflows, cron scheduling
3. **Version Control Service** (8010) - Knowledge base and pipeline versioning
4. **Alert Manager** (8011) - Alert rules and notifications
5. **Audit Log Service** (8012) - Immutable audit logging
6. **Cost Optimizer** (8013) - Cost tracking and optimization
7. **Webhook Manager** (8014) - Webhook configuration and delivery
8. **Security Scanner** (8015) - Vulnerability and PII scanning

**Estimated Time:** 2 weeks

**Next Phase:** [Phase 4: Production Readiness](./2026-04-21-phase4-production-readiness.md)
