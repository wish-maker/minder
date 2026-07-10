# Hardware Resource Optimization (Raspberry Pi 4 / ARM)

**Version:** 2.0
**Last Updated:** 2026-07-10

---

## Overview

Minder's deployment target is a single **Raspberry Pi 4 (RPi-4-01, ARM)**. This is a
**development environment**; production hardening is not yet applied. Everything runs in
Docker via `docker/compose/docker-compose.yml` (the hand-maintained source of truth) and
is provisioned with `bash setup.sh`.

On a single Pi, the two scarce resources are **RAM** and **CPU**. LLM inference (Ollama)
dominates both. This guide covers the resource controls that actually exist in the compose
file today, plus practical tuning for the Pi.

> No synthetic benchmark numbers are quoted here. Measure on your own hardware — see
> `monitoring.md` for how (cAdvisor + node-exporter + Grafana).

---

## Resource Limits in Compose

Docker Compose `deploy.resources` limits are used to keep any one service from starving
the Pi. Today the only service with an **active** limit is the API gateway:

```yaml
# docker/compose/docker-compose.yml — api-gateway
services:
  api-gateway:
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '2'
        reservations:
          memory: 512M
          cpus: '0.5'
```

Other heavyweight services (e.g. Ollama) have `deploy.resources` blocks present but
**commented out** — they were sized for a GPU host (`cpus: '4.0'`, `memory: 8G`) and are
not appropriate for the Pi. If you enable them, scale the numbers down to fit 8 GB total
RAM.

To add a limit to another service, edit the compose file directly:

```yaml
services:
  <service>:
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
```

> Note: `deploy.resources.reservations` for CPU/memory are honored by `docker compose`;
> `deploy.replicas` is a Swarm-only field and is **not** how Minder scales (there is no
> Swarm here).

---

## Ollama Model Sizing (the biggest lever)

Ollama is the single largest consumer of RAM. Model choice is the most important tuning
decision on a Pi.

### How models are configured

```yaml
# docker/compose/docker-compose.yml — ollama
environment:
  - OLLAMA_PULL_MODELS=${OLLAMA_MODELS:-llama3.2,nomic-embed-text}
  - OLLAMA_AUTOMATIC_PULL=${OLLAMA_AUTOMATIC_PULL:-true}
  - OLLAMA_HOST=0.0.0.0
  - OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-}
  - OLLAMA_ORIGINS=*
```

- **`OLLAMA_PULL_MODELS`** (driven by `OLLAMA_MODELS` in `./.env`) is the list of models
  to auto-pull. Default: `llama3.2` (chat/generation) + `nomic-embed-text` (RAG
  embeddings). This is **not** the storage directory — the server stores models under
  `/root/.ollama/models`, which is the `ollama_data` volume.
- **`OLLAMA_BASE_URL`** controls local vs. remote inference:
  - **empty** → the internal `minder-ollama` container runs (profile
    `internal-ollama`); models run *on the Pi*.
  - **set** (e.g. to a beefier host) → the container is inactive and inference is
    offloaded. Use `bash setup.sh ollama-mode` to switch. Offloading is the recommended
    way to run large models without stressing the Pi.

### Model-size tradeoffs on a Pi 4 (8 GB)

- Prefer **small, quantized** models. `llama3.2` (3B) and `nomic-embed-text` are sensible
  defaults for a Pi.
- Larger models (7B+) will run but are slow and memory-hungry on ARM CPU-only inference;
  they may swap or OOM alongside the rest of the stack.
- If you need larger models, set `OLLAMA_BASE_URL` to an external/native host rather than
  running them in the Pi container.

### GPU variables

The compose file carries GPU-oriented env vars for hosts that have an accelerator:

```yaml
environment:
  - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-all}
  - GPU_MEMORY_UTILIZATION=${GPU_MEMORY_UTILIZATION:-0.9}
```

The Raspberry Pi 4 has **no CUDA GPU**, so these have no effect on the Pi. The NVIDIA
`runtime:` line and the GPU `reservations` block are commented out for the same reason;
they only matter if you redeploy to a GPU host.

---

## Other Service Tuning Knobs

### Neo4j heap

Neo4j is memory-sensitive. It is pinned to a small heap so it coexists with the rest of
the stack on the Pi:

```yaml
# docker/compose/docker-compose.yml — neo4j
environment:
  NEO4J_dbms_memory_heap_initial__size: 512m
  NEO4J_dbms_memory_heap_max__size: 1G
```

### Redis

Redis is `redis:8.8.0-alpine`. If memory pressure appears, cap it with `--maxmemory` and
an eviction policy in the service's `command:` (e.g. `--maxmemory 256mb
--maxmemory-policy allkeys-lru`). Keep the cap well under the Pi's free RAM.

### PostgreSQL

`postgres:18.4-trixie`. On a Pi, leave the defaults modest — do not set large
`shared_buffers`/`work_mem` values sized for a server; they will contend with Ollama and
the JVM (Neo4j).

---

## Monitoring Resource Usage

Use the built-in observability stack rather than a bespoke Python monitor:

- **node-exporter** — host CPU / memory / disk / network of the Pi
- **cadvisor** — per-container CPU / memory
- **Grafana** (`:3000`) — visualize both

```bash
# Quick live snapshot
docker stats --no-stream | grep minder

# Host memory
free -h

# Disk
df -h
```

See `monitoring.md` for the full stack and how to wire alerts through Alertmanager.

---

## Practical Guidance for the Pi 4

1. **Watch total RAM first.** 8 GB is shared across ~31 containers plus Ollama. The API
   gateway is capped at 2 G; Ollama and Neo4j are the next biggest consumers.
2. **Offload big models.** Point `OLLAMA_BASE_URL` at an external host for anything larger
   than a small quantized model.
3. **Use a good SD card or (better) USB-SSD boot.** Vector (Qdrant) and graph (Neo4j)
   workloads are I/O sensitive; slow storage shows up as latency.
4. **Don't over-provision limits.** Reservations that exceed available RAM will prevent
   containers from scheduling.
5. **Keep an eye on swap.** Heavy swapping on a Pi tanks performance far more than on a
   server.

---

## Not Implemented (was previously documented)

Earlier revisions of this guide described a `src.shared.resource_optimizer` Python module
(ResourceMonitor, ConnectionPoolOptimizer, AdaptiveExecutor, etc.) and quoted
percentage-based performance gains. **That module does not exist in the codebase** and the
numbers were not measured — both have been removed. Resource observability today is
provided by the Prometheus/Grafana/exporters stack described above.

---

**Last Updated:** 2026-07-10
