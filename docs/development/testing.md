# Testing and Quality Guide

**Version:** 1.0
**Last Updated:** 2026-07-10

---

## Table of Contents

1. [Overview](#overview)
2. [Test Structure](#test-structure)
3. [Test Categories](#test-categories)
4. [Running Tests](#running-tests)
5. [Test Coverage](#test-coverage)
6. [Testing Against Services](#testing-against-services)
7. [Code Quality](#code-quality)
8. [CI Integration](#ci-integration)

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

A `docker-compose.test.yml` at the repo root brings up the dependencies needed for
integration and e2e runs.

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
etc.) started via `docker-compose.test.yml`.

```bash
# Bring up test dependencies
docker compose -f docker-compose.test.yml up -d

# Run integration tests
pytest tests/integration/ -v

# Tear down
docker compose -f docker-compose.test.yml down -v
```

### 3. End-to-End Tests (`tests/e2e/`)

Exercise complete workflows across multiple services.

```bash
pytest tests/e2e/ -v
```

### 4. Performance Tests (`tests/performance/`)

Measure throughput / latency under load. These are the slowest tests.

```bash
pytest tests/performance/ -v
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

# Type check
mypy src/
```

---

## CI Integration

CI runs across a small set of workflows:

- **`quality.yml`** — fast gate: Black, isort, mypy, plus light bandit/safety scans.
- **`ci.yml`** — the test suite (pytest).
- **`security.yml`** — deeper scans (CodeQL, Trivy).
- **`docker-image-update.yml`** — third-party image update automation.

Tests run on Python 3.11 / 3.12 to match the service runtimes.

---

## Quality Checklist

### Before Committing
- [ ] Tests pass (`pytest`)
- [ ] Formatted (`black --check src/`)
- [ ] Imports sorted (`isort --check-only src/`)
- [ ] Type checked (`mypy src/`)

### Before Merging
- [ ] CI green (quality + tests + security)
- [ ] Documentation updated if behavior changed
- [ ] Change reviewed

---

## Getting Help

- pytest: https://docs.pytest.org/
- coverage: https://coverage.readthedocs.io/

---

**Last Updated:** 2026-07-10
