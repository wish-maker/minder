# Testing and Quality Guide

**Version:** 1.0
**Last Updated:** 2026-08-08

---

## Table of Contents

1. [Overview](#overview)
2. [Test Structure](#test-structure)
3. [Test Categories](#test-categories)
4. [Running Tests](#running-tests)
5. [Test Coverage](#test-coverage)
6. [Fixtures](#fixtures)
7. [Writing Tests](#writing-tests)
8. [Testing Against Services](#testing-against-services)
9. [Code Quality](#code-quality)
10. [CI Integration](#ci-integration)
11. [Debugging](#debugging)

---

## Overview

This guide covers testing for the Minder platform. Services are Python (3.11 / 3.12)
FastAPI apps; tests are written with **pytest**.

pytest is configured in the **root `pyproject.toml`** with `asyncio_mode = "auto"`, so
`async def` tests run without an explicit `@pytest.mark.asyncio` marker.

---

## Test Structure

Tests live under `tests/` at the repo root:

```
minder/
└── tests/
    ├── fixtures/        # Shared test data and fixtures
    ├── unit/            # Fast, isolated unit tests
    ├── integration/     # Component/service interaction tests
    ├── e2e/             # End-to-end workflow tests
    ├── performance/     # Performance / load tests
    └── manual/          # Manual / exploratory test scripts
```

A `docker/docker-compose.test.yml` brings up the dependencies needed for
integration and e2e runs (local only — CI uses GitHub Actions `services:`).

---

## Test Categories

### 1. Unit Tests (`tests/unit/`)

Test individual functions/classes in isolation. Fast, no external dependencies,
databases and APIs mocked.

```python
def test_validate_plugin_name():
    assert validate_plugin_name("test-plugin") == "test-plugin"
    with pytest.raises(ValueError):
        validate_plugin_name("")
```

```bash
pytest tests/unit/ -v
```

### 2. Integration Tests (`tests/integration/`)

Test interaction between components with real dependencies (Postgres, Redis, Qdrant,
etc.) started via `docker/docker-compose.test.yml`.

```bash
# Bring up test dependencies
docker compose -f docker/docker-compose.test.yml up -d

# Run integration tests
pytest tests/integration/ -v

# Tear down
docker compose -f docker/docker-compose.test.yml down -v
```

### 3. End-to-End Tests (`tests/e2e/`)

Real cross-service workflows — no mocks, no Docker. A session-scoped fixture
(`conftest.py`'s `live_stack`) starts api-gateway, plugin-registry,
rag-pipeline, marketplace, model-management, and graph-rag as real `uvicorn`
subprocesses bound to `127.0.0.1`, wired together via the same env vars
`docker-compose.yml` uses (just `localhost` instead of `minder-<service>`
hostnames), against a real Postgres/Redis/Qdrant/Neo4j and a small
deterministic fake-Ollama stub (`fake_ollama.py`) — real Ollama (model pull +
inference) is the slow, non-deterministic part; Minder's own code only needs
to be tested for correctly *calling* Ollama, not for model output quality.

Covers: harness/health smoke, plugin discovery + read-only action invocation
(the #254 GET-unauthenticated/POST-JWT-gated split, direct and via the
gateway proxy), the full RAG document lifecycle (create KB → upload → query
→ cleanup) against a real Qdrant, the chat + tool-calling dispatch loop for
both native `tool_calls` and the #250 content-embedded-JSON fallback, and
downstream error propagation (404/400/503) through the gateway's generic
proxy. Auth (register/login/JWT) is already covered for real in
`tests/integration/test_auth_e2e.py` and isn't reproduced here. Deliberately
**not** covered (no real feature exists to test): rate-limit thresholds,
security fuzzing, circuit breakers, load balancing, message queues — see
issue #318.

Requires a real Postgres, Redis, Qdrant, and Neo4j reachable at
`127.0.0.1:5432/6379/6333/7687` (matching `ci.yml`'s `e2e-tests` job — locally,
start them yourself with matching credentials; see the `E2E_*` env vars at
the top of `conftest.py` to point elsewhere).

```bash
pytest tests/e2e/ -v
```

#### Tool-calling model reliability (#328)

A live audit (`tests/manual/test_real_user_journeys.py`) found the deployed
default model, `granite3-moe:latest`, answering a confident, wrong,
hallucinated Bitcoin price instead of calling the real crypto plugin — no
signal anywhere distinguished that from a real tool-backed answer (fixed:
every chat response now carries `minder_tools_offered`/
`minder_tool_calls_made`, see `routes/ai.py`'s `_chat_with_tools`). Ollama's
own `capabilities` metadata (`GET /v1/models/{id}`, promoted from
`ShowResponse` in `model-management/routes/models_api.py`) reports `tools`
support for essentially every installed model, `granite3-moe` included —
capability metadata alone does **not** predict whether a model actually
invokes a tool for a naturally-phrased question. Only a live check
(`minder_tool_calls_made` on a real `minder_tools: true` request) does.

Live-tested on the Raspberry Pi host against the same "What is the current
price of bitcoin?" question:

| Model | Reports `tools` capability | Actually invoked the real tool live |
|---|---|---|
| `granite3-moe:latest` (previous default) | yes | **no** — hallucinated a price |
| `command-r:latest` | yes | yes — real price |
| `llama3.2:latest` | yes | yes — real price |
| `qwen3:30b` | yes | yes — real price |
| `mistral-nemo:12b` | yes | yes — real price |

**Recommendation:** use `command-r:latest`, `llama3.2:latest`, `qwen3:30b`,
or `mistral-nemo:12b` — not `granite3-moe` — for any chat flow with
`minder_tools: true`. Switching the deployed default is an ops decision, not
made here; re-verify with a live check (not just the capabilities field)
before trusting a new model with tool-augmented chat.

### 4. Performance Tests (`tests/performance/`)

Home for throughput / latency tests (mark them `@pytest.mark.load`/`@pytest.mark.slow`;
not part of the default CI suite). No harness ships by default — see
[`tests/performance/README.md`](../../tests/performance/README.md) for the external
Locust approach.

```bash
pytest tests/performance/ -v -m load
```

### 5. Manual Tests (`tests/manual/`)

Scripts for manual verification and exploratory checks. Not run in CI; execute
individually as needed.

---

## Running Tests

```bash
# All tests
pytest

# Verbose
pytest -v

# A single directory
pytest tests/unit/ -v

# A single file
pytest tests/unit/test_validators.py -v

# A single test
pytest tests/unit/test_validators.py::TestValidators::test_accepts_valid_name -v

# By keyword
pytest -k "validate_plugin"
```

### By Marker

Markers registered in the root `pyproject.toml` — `integration`, `e2e`, `slow`,
`security`:

```bash
pytest -m integration
pytest -m "not integration"    # skip integration tests
```

### Parallel Execution

```bash
# Requires pytest-xdist
pytest -n auto
```

---

## Test Coverage

Coverage is measured with `pytest-cov`:

```bash
# Terminal report with missing lines
pytest --cov=src --cov-report=term-missing

# HTML report
pytest --cov=src --cov-report=html

# XML report (for CI)
pytest --cov=src --cov-report=xml
```

> Coverage targets/thresholds are being evaluated (see repo issue tracker). Measure the
> current baseline before asserting a specific percentage — do not assume a fixed number.

---

## Fixtures

Shared fixtures live in `tests/conftest.py`. Commonly used ones:

| Fixture | Purpose |
|---|---|
| `mock_redis`, `mock_redis_client`, `mock_redis_pipeline` | Mocked Redis for unit tests |
| `mock_postgres_pool` | Mocked Postgres pool for unit tests |
| `test_db_pool`, `test_db_connection` | Real Postgres pool/connection (integration) |
| `test_redis`, `redis_client` | Real Redis client (integration) |
| `test_client`, `gateway_test_client` | HTTP test clients |
| `test_token`, `test_headers` | A JWT and `Authorization`-bearing headers |

```python
def test_redis_operation(mock_redis):
    mock_redis.get.return_value = "test_value"
    assert mock_redis.get("my_key") == "test_value"
```

---

## Writing Tests

### Unit test (mocked, no external services)

```python
from unittest.mock import patch

from shared.utils.redis_client import create_redis_client

def test_redis_client_factory():
    with patch("redis.Redis") as mock_redis:
        client = create_redis_client(host="localhost")
        assert client is not None
```

### Integration test (real service, skip if unavailable)

```python
import pytest

@pytest.mark.integration
def test_real_redis_connection(redis_client):
    try:
        assert redis_client.ping() is True
    except ConnectionError:
        pytest.skip("Redis not available")
```

### Async test

With `asyncio_mode = "auto"`, an `async def` test just works:

```python
async def test_async_operation():
    result = await async_function()
    assert result is not None
```

### Testing an endpoint

```python
def test_health_endpoint(gateway_test_client):
    response = gateway_test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] in ("healthy", "degraded", "unhealthy")
```

### Best Practices

- Descriptive test names (`test_login_rejects_bad_password`, not `test_1`).
- Arrange–Act–Assert structure.
- Mark tests that hit real services with `@pytest.mark.integration` and skip
  gracefully when the dependency is absent.
- Use `pytest.raises` for expected failures:

```python
with pytest.raises(ValueError, match="Invalid input"):
    process_invalid_data("bad input")
```

---

## Testing Against Services

Application services run as Docker containers named `minder-<service>`. Host-exposed app
services (api-gateway :8000, plugin-registry :8001, marketplace :8002,
plugin-state-manager :8003, rag-pipeline :8004, model-management :8005, tts-stt :8006,
graph-rag :8008) expose a `/health` endpoint:

```bash
curl http://localhost:8000/health   # api-gateway
curl http://localhost:8004/health   # rag-pipeline
curl http://localhost:8008/health   # graph-rag
```

Storage backends (postgres, redis, qdrant, neo4j, minio, rabbitmq, schema-registry) are
**internal-only** — reach them by exec'ing into the container or via Traefik, not by a
host port.

---

## Code Quality

Formatting, import order, and type/security checks are run by CI (`quality.yml`) and
configured in the root `pyproject.toml`. See [code-style.md](code-style.md) for details.

```bash
# Format
black src/

# Check formatting
black --check src/

# Import order
isort --check-only src/

# Type check — per-service ("mypy src/" collides on duplicate top-level modules)
(cd src/services/<service> && mypy . --ignore-missing-imports)
```

---

## CI Integration

CI runs across a small set of workflows:

- **`quality.yml`** — fast gate: Black, isort, **flake8**, **mypy (real gate, per-service, no `|| true`)**, bandit, safety, shellcheck, hadolint, secret scan.
- **`ci.yml`** — unit tests → {**container smoke test** (builds + `docker compose up --wait`
  on 7 of the 8 core service images — the only job that actually runs Minder's own containers),
  integration tests → e2e tests} → notify; integration/e2e deps come via GitHub Actions
  `services:`, e2e runs each service as a bare process (no Docker) with a deterministic
  fake-Ollama stub.
- **`security.yml`** — deeper scans (CodeQL, Trivy).
- **`dependency-updates.yml`** — weekly issue-only dependency check, both halves: 3rd-party
  Docker image updates and Python (pip) pin updates.

Tests run on Python 3.11 / 3.12 to match the service runtimes.

---

## Debugging

```bash
pytest -s          # show print output
pytest --pdb       # drop into debugger on failure
pytest -x          # stop at first failure
```

```python
def test_with_logging(caplog):
    with caplog.at_level("INFO"):
        logger.info("Test message")
    assert "Test message" in caplog.text
```

---

## Quality Checklist

### Before Committing
- [ ] Tests pass (`pytest`)
- [ ] Formatted (`black --check src/`)
- [ ] Imports sorted (`isort --check-only src/`)
- [ ] Type checked (per-service: `cd src/services/<svc> && mypy .`)

### Before Merging
- [ ] CI green (quality + tests + security)
- [ ] Documentation updated if behavior changed
- [ ] Change reviewed

---

## Getting Help

- pytest: https://docs.pytest.org/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- coverage: https://coverage.readthedocs.io/
- FastAPI testing: https://fastapi.tiangolo.com/tutorial/testing/

---

**Last Updated:** 2026-08-08
