# Minder Platform - Testing Guide

How tests are organised and run for the Minder platform.

## Test layout

Tests live under `tests/`, split by kind:

```
tests/
├── conftest.py         # shared fixtures (db pools, redis, http clients, tokens)
├── fixtures/           # static test data (e.g. valid/invalid manifest JSON)
├── unit/               # fast, isolated tests (mocks; no external services)
├── integration/        # tests against real services (Redis, Postgres, gateway proxy, ...)
├── e2e/                # end-to-end flows (full plugin lifecycle, service integration)
├── performance/        # load testing (Locust — locustfile.py)
└── manual/             # scripts run by hand for validation (see manual/README.md)
```

## Pytest configuration

Configuration lives in the **root `pyproject.toml`**:

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
```

`asyncio_mode = "auto"` means async test functions are detected and run
automatically — you generally do **not** need to decorate every coroutine test
with `@pytest.mark.asyncio` (some existing tests still carry it; that is
harmless).

> There is no repo-wide coverage threshold or custom marker registry configured
> in `pyproject.toml` today. Markers such as `integration`, `slow`, and
> `security` are used in the code as plain markers; coverage is opt-in on the
> command line (see below).

## Running tests

```bash
# Everything
pytest

# Verbose
pytest -v

# A directory
pytest tests/unit
pytest tests/integration

# A single file / test
pytest tests/unit/test_module_management.py
pytest tests/unit/test_module_management.py::TestSomething::test_case
```

### By marker

Markers currently used in the suite include `integration`, `slow`, and
`security` (plus `asyncio` on some tests):

```bash
pytest -m integration
pytest -m slow
pytest -m "not integration"    # skip integration tests
```

### With coverage

Coverage is not enabled by default; pass it explicitly when you want a report
(requires `pytest-cov`):

```bash
pytest --cov=src --cov-report=term
pytest --cov=src --cov-report=html    # htmlcov/index.html
pytest --cov=src --cov-report=xml     # for CI
```

---

## Fixtures

Shared fixtures are defined in `tests/conftest.py`. Commonly used ones:

| Fixture | Purpose |
|---|---|
| `mock_redis`, `mock_redis_client`, `mock_redis_pipeline` | Mocked Redis for unit tests |
| `mock_postgres_pool` | Mocked Postgres pool for unit tests |
| `test_db_pool`, `test_db_connection` | Real Postgres pool/connection (integration) |
| `test_redis`, `redis_client` | Real Redis client (integration) |
| `test_client`, `gateway_test_client` | HTTP test clients |
| `test_token`, `test_headers` | A JWT and `Authorization`-bearing headers |

Example:

```python
def test_redis_operation(mock_redis):
    mock_redis.get.return_value = "test_value"
    assert mock_redis.get("my_key") == "test_value"
```

---

## Writing tests

### Unit test (mocked, no external services)

```python
from unittest.mock import patch

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

### Best practices

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

## Load / performance testing

Load tests use Locust (`tests/performance/locustfile.py`):

```bash
pip install locust
locust -f tests/performance/locustfile.py --host http://localhost:8000
```

Remember the platform targets a Raspberry Pi 4 and the LLM is usually the
bottleneck — see [performance.md](./performance.md).

---

## Manual validation

`tests/manual/` holds scripts run by hand (database-write checks, end-to-end
validation, etc.). See `tests/manual/README.md`. These are not part of the
automated `pytest` run by default.

---

## CI

Tests run in CI on push and pull request. The pipeline installs dependencies
from `src/requirements/`, then runs the suite. See the workflows under
`.github/workflows/` (the `ci` workflow runs tests; `quality` runs linters).

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

## Resources

- [Pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [API documentation](./api.md)

---

**Last Updated:** 2026-07-10
