# Minder Platform - Testing Guide

Comprehensive testing guide for Minder platform services and components.

## 🧪 Testing Infrastructure

### Project Structure

```
tests/
├── __init__.py
├── conftest.py                    # Pytest configuration and fixtures
├── test_shared_utils_redis.py    # Redis utilities tests
├── test_shared_utils_cors.py     # CORS utilities tests
├── test_shared_utils_service_urls.py  # Service URL tests
└── test_shared_models_responses.py  # Response model tests
```

### Running Tests

#### Run All Tests
```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=services/shared --cov-report=html
```

#### Run Specific Tests
```bash
# Run specific test file
pytest tests/unit/test_module_management.py

# Run specific test class
pytest tests/unit/test_module_management.py::TestCreateRedisClient

# Run specific test
pytest tests/unit/test_module_management.py::TestCreateRedisClient::test_create_redis_client_basic
```

#### Run by Marker
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run tests requiring Redis
pytest -m redis

# Run slow tests
pytest -m slow
```

---

## 📋 Test Categories

### Unit Tests (`@pytest.mark.unit`)

Fast tests with no external dependencies.

**Example:**
```python
@pytest.mark.unit
def test_redis_client_factory():
    """Test Redis client factory"""
    with patch("redis.Redis") as mock_redis:
        client = create_redis_client(host="localhost")
        assert client is not None
```

### Integration Tests (`@pytest.mark.integration`)

Slower tests with real external services.

**Example:**
```python
@pytest.mark.integration
@pytest.mark.redis
def test_real_redis_connection():
    """Test connection to real Redis"""
    try:
        client = create_redis_client(host="redis")
        assert client.ping() is True
    except ConnectionError:
        pytest.skip("Redis not available")
```

### Slow Tests (`@pytest.mark.slow`)

Performance and stress tests.

**Example:**
```python
@pytest.mark.slow
def test_redis_performance_under_load():
    """Test Redis performance under load"""
    client = create_redis_client(host="redis")

    start = time.time()
    for i in range(1000):
        client.set(f"key-{i}", f"value-{i}")

    duration = time.time() - start
    assert duration < 1.0  # Should complete in < 1 second
```

---

## 🛠️ Fixtures

### Available Fixtures

#### `test_settings`
Test settings object with safe defaults.

```python
def test_with_settings(test_settings):
    assert test_settings.REDIS_HOST == "localhost"
```

#### `mock_redis`
Mock Redis client for testing.

```python
def test_redis_operation(mock_redis):
    mock_redis.get.return_value = "test_value"
    result = mock_redis.get("my_key")
    assert result == "test_value"
```

#### `async_client`
Async HTTP client for testing.

```python
async def test_async_call(async_client):
    response = await async_client.get("http://localhost:8000/health")
    assert response.status_code == 200
```

#### `fastapi_app`
Test FastAPI app instance.

```python
def test_fastapi_endpoint(fastapi_app):
    client = TestClient(fastapi_app)
    response = client.get("/health")
    assert response.status_code == 200
```

#### `test_client`
Test client for FastAPI apps.

```python
def test_endpoint(test_client):
    response = test_client.get("/test")
    assert response.json() == {"message": "test"}
```

---

## 📝 Writing Tests

### Test Structure

```python
import pytest
from unittest.mock import Mock, patch

class TestMyFeature:
    """Test suite for MyFeature"""

    def test_basic_functionality(self):
        """Test basic functionality"""
        # Arrange
        input_data = {"key": "value"}

        # Act
        result = process(input_data)

        # Assert
        assert result is not None
        assert result["status"] == "success"

    def test_with_mock(self, mock_redis):
        """Test with mocked dependency"""
        mock_redis.get.return_value = "mocked_value"

        result = get_data("my_key")

        assert result == "mocked_value"
        mock_redis.get.assert_called_once_with("my_key")

    @pytest.mark.integration
    def test_integration(self):
        """Integration test with real services"""
        try:
            client = create_real_client()
            assert client.ping() is True
        except ConnectionError:
            pytest.skip("Service not available")
```

### Best Practices

#### 1. Use Descriptive Names
```python
# ✅ Good
def test_redis_client_returns_none_for_nonexistent_key()

# ❌ Bad
def test_redis_1()
```

#### 2. Follow Arrange-Act-Assert Pattern
```python
def test_user_creation():
    # Arrange
    user_data = {"name": "John", "email": "john@example.com"}

    # Act
    user = create_user(user_data)

    # Assert
    assert user.id is not None
    assert user.name == "John"
```

#### 3. Use Appropriate Markers
```python
@pytest.mark.unit
def test_fast_calculation():  # No external deps
    ...

@pytest.mark.integration
@pytest.mark.redis
def test_redis_storage():  # Requires Redis
    ...
```

#### 4. Handle Expected Failures
```python
def test_invalid_input_raises_error():
    with pytest.raises(ValueError, match="Invalid input"):
        process_invalid_data("bad input")
```

#### 5. Use Fixtures for Setup
```python
def test_with_database(mock_db_pool):
    # Use fixture instead of manual setup
    result = mock_db_pool.fetch_one("SELECT 1")
    assert result is not None
```

---

## 🎯 Testing Examples

### Testing API Endpoints

```python
from fastapi.testclient import TestClient
from services.shared.models import HealthCheckResponse

def test_health_endpoint(test_client):
    """Test health check endpoint"""
    response = test_client.get("/health")

    assert response.status_code == 200
    data = response.json()

    assert data["service"] == "my-service"
    assert data["status"] in ["healthy", "unhealthy", "degraded"]

def test_health_endpoint_with_model(test_client):
    """Test health check with response model validation"""
    response = test_client.get("/health")

    assert response.status_code == 200

    # Validate against Pydantic model
    health_data = HealthCheckResponse(**response.json())
    assert health_data.service == "my-service"
```

### Testing with Mocks

```python
from unittest.mock import Mock, patch

def test_service_with_mocked_redis():
    """Test service with mocked Redis"""
    # Mock Redis client
    mock_redis = Mock()
    mock_redis.get.return_value = "cached_value"

    with patch("create_redis_client", return_value=mock_redis):
        service = MyService()
        result = service.get_cached_data("key")

    assert result == "cached_value"
    mock_redis.get.assert_called_once_with("key")
```

### Testing Validation

```python
import pytest
from services.shared.utils.validation import validate_identifier

def test_validate_identifier_valid():
    """Test valid identifier"""
    result = validate_identifier("my_plugin-123")
    assert result == "my_plugin-123"

def test_validate_identifier_invalid_chars():
    """Test identifier with invalid characters"""
    with pytest.raises(ValueError, match="must contain only"):
        validate_identifier("my plugin!")

def test_validate_identifier_too_long():
    """Test identifier exceeding max length"""
    long_id = "a" * 101
    with pytest.raises(ValueError, match="must not exceed"):
        validate_identifier(long_id)
```

### Testing Async Code

```python
import pytest

@pytest.mark.asyncio
async def test_async_operation():
    """Test async function"""
    result = await async_function()
    assert result is not None

@pytest.mark.asyncio
async def test_async_with_client(async_client):
    """Test async HTTP call"""
    response = await async_client.get("http://localhost:8000/health")
    assert response.status_code == 200
```

---

## 📊 Coverage Goals

### Target Coverage

| Component | Target Coverage | Current Coverage |
|------------|-----------------|-------------------|
| Shared Utils | 90% | TBD |
| Shared Models | 95% | TBD |
| Services | 70% | TBD |
| Overall | 80% | TBD |

### Generating Coverage Reports

```bash
# Generate HTML coverage report
pytest --cov=services/shared --cov-report=html

# Generate terminal coverage report
pytest --cov=services/shared --cov-report=term

# Generate XML coverage report (for CI)
pytest --cov=services/shared --cov-report=xml
```

### Coverage Exclusions

```python
# Exclude from coverage
@pytest.mark.coverage_exempt
def test_helper_function():
    """Helper function not needing coverage"""
    ...
```

---

## 🚀 CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      redis:
        image: redis:latest
        ports:
          - 6379:6379

    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-cov

      - name: Run unit tests
        run: pytest -m unit --cov=services/shared

      - name: Run integration tests
        run: pytest -m integration

      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## 🔧 Debugging Tests

### Running Tests in Debug Mode

```bash
# Run with pdb debugger
pytest --pdb

# Run with pdb on failure
pytest --pdb-failures

# Show print statements
pytest -s
```

### Logging Test Output

```python
import logging

def test_with_logging(caplog):
    """Test with log capture"""
    with caplog.at_level(logging.INFO):
        logger.info("Test message")

    assert "Test message" in caplog.text
```

---

## 📋 Test Checklist

Before committing code, ensure:

- [ ] All unit tests pass
- [ ] Code coverage ≥ target
- [ ] No skipped tests without reason
- [ ] Tests follow naming conventions
- [ ] Fixtures used appropriately
- [ ] Async tests marked with `@pytest.mark.asyncio`
- [ ] Integration tests marked with `@pytest.mark.integration`
- [ ] Slow tests marked with `@pytest.mark.slow`

---

## 🎓 Resources

### Documentation
- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Pydantic Validation](https://pydantic-docs.helpmanual.io/usage/validators/)

### Internal Resources
- [Shared Components README](../../src/shared/README.md)
- [API Documentation](./api.md)

---

**Last Updated:** 2025-01-11  
**Test Framework:** Pytest 7.0+  
**Python Version:** 3.11+
