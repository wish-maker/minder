# Minder Platform - Performance & Tuning Guide

Practical guidance for understanding and tuning the performance of the Minder
platform.

> **No benchmark numbers here are invented.** Minder runs as a **development
> deployment on a Raspberry Pi 4 (ARM)**. Real-world performance depends heavily
> on the hardware you run it on, the LLM model you choose, and how many services
> are active at once. Measure on your own hardware rather than relying on
> generic figures. Earlier versions of this doc contained fabricated benchmark
> tables (fixed response times, throughput targets, etc.) — those have been
> removed.

---

## What dominates performance

On a Raspberry Pi 4 (4 cores, limited RAM, no discrete GPU), the biggest factors
are, in rough order:

1. **LLM inference (Ollama).** Model size and quantization dominate everything.
   A 7B model on a Pi is slow and memory-hungry; small quantized models are far
   more usable. This is almost always the bottleneck for RAG and chat.
2. **Memory pressure.** 31 containers plus an LLM can exceed available RAM,
   causing swap and severe slowdowns. Trim what you don't need.
3. **Vector search (Qdrant)** and **graph queries (Neo4j)** for RAG / graph-RAG.
4. **Startup time.** Cold starts (especially services that download models or
   spaCy data) take a while; this is one-time per container start.

---

## Tuning levers

### 1. Choose a smaller / quantized Ollama model

Model choice is the single highest-impact lever. Prefer small, quantized models
on constrained ARM hardware.

- Models are pulled via `OLLAMA_PULL_MODELS` (set in the root `./.env`).
- Ollama storage lives in the `/root/.ollama/models` volume.
- List what is loaded:
  ```bash
  curl http://localhost:11434/api/tags   # when running the local ollama container
  ```

### 2. Local vs. external Ollama

Ollama runs in one of two modes, controlled by `OLLAMA_BASE_URL`:

- **empty** → the profile-gated `internal-ollama` container runs on the Pi.
- **set** → inference is delegated to an external / native host (the container
  stays inactive).

If the Pi is underpowered for your model, pointing `OLLAMA_BASE_URL` at a more
capable machine is often the most effective "optimization" available.

### 3. Container resource limits

Set CPU/memory limits and reservations in
`docker/compose/docker-compose.yml` (`deploy.resources` / `mem_limit`) to keep a
runaway service from starving the LLM. On a memory-constrained Pi, stopping
services you are not using is more effective than micro-tuning limits.

### 4. Qdrant (vector DB)

- Keep embedding dimensionality reasonable for the model in use.
- Reasonable chunk sizes in the RAG pipeline reduce vector count and speed up
  retrieval.

### 5. Neo4j (graph-RAG)

- Ensure appropriate indexes/constraints exist for the entities you query.
- Constrain graph-retrieval depth for the `/retrieve` and `/entity-context`
  endpoints.

### 6. Redis caching and rate limiting

The API Gateway already uses Redis for rate limiting (60s window, fail-open).
Redis is also available for caching expensive results in services where it
helps. Keep Redis healthy — if it degrades, the rate limiter fails open (allows
traffic) rather than blocking.

---

## Application-level patterns

These are general FastAPI/async best practices the services already follow and
that you should keep to when extending them.

### Use async I/O and reuse clients

```python
# Reuse a single httpx.AsyncClient with connection pooling
http_client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
    timeout=httpx.Timeout(30.0, connect=10.0),
)
```

Avoid creating a new client per request, and avoid blocking calls
(`time.sleep`, sync DB drivers) inside async handlers.

### Paginate list endpoints

Always bound result sets (`limit`/`offset`) rather than returning everything.

### Avoid N+1 queries

Prefer a single query with a join / `= ANY($1)` over per-item lookups in a loop.

---

## Monitoring

The platform ships an observability stack — use it to get **real** numbers for
your deployment instead of guessing.

- **Prometheus** (`http://localhost:9090`) scrapes service `/metrics` endpoints
  and node/container exporters.
- **Grafana** (`http://localhost:3000`) for dashboards.
- **Jaeger** (`http://localhost:16686`) for distributed tracing.
- **cAdvisor / node-exporter** expose per-container CPU/memory so you can spot
  which service is under pressure.

Quick resource snapshot:
```bash
docker stats --no-stream
```

Useful metric families exposed by the services:
```
http_requests_total{method,endpoint,status}
http_request_duration_seconds{method,endpoint}
```

---

## Profiling (when you need detail)

```bash
pip install pyinstrument
pyinstrument python -m uvicorn main:app
```

For a quick in-process profile use the stdlib:
```python
import cProfile, pstats
profiler = cProfile.Profile()
profiler.enable()
# ... exercise the code path ...
profiler.disable()
pstats.Stats(profiler).sort_stats("time").print_stats(10)
```

---

## Load testing

If you want throughput numbers, generate them against your own deployment with
a tool like [Locust](https://locust.io/) — and remember the LLM will usually be
the limiting factor, so test the RAG/query paths realistically (with the model
you actually run).

```bash
pip install locust
locust -f locustfile.py --host http://localhost:8000
```

---

## Resources

- [FastAPI performance tips](https://fastapi.tiangolo.com/deployment/concepts/)
- [Ollama documentation](https://github.com/ollama/ollama)
- [Qdrant documentation](https://qdrant.tech/documentation/)
- [Neo4j performance guide](https://neo4j.com/docs/)

---

**Last Updated:** 2026-07-10
