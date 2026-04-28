# 🧪 Comprehensive Testing and Quality Guide

**Version:** 1.0
**Last Updated:** 2026-04-27

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Test Structure](#test-structure)
3. [Test Categories](#test-categories)
4. [Running Tests](#running-tests)
5. [Test Coverage](#test-coverage)
6. [Load Testing](#load-testing)
7. [Security Testing](#security-testing)
8. [Performance Testing](#performance-testing)
9. [Code Quality](#code-quality)
10. [CI/CD Integration](#cicd-integration)

---

## 🎯 Overview

This guide provides comprehensive testing strategies and quality standards for the Minder project.

### Quality Goals

- **Test Coverage:** 93% achieved (118 tests passing)
- **Response Time:** <100ms (p95)
- **Success Rate:** 95% minimum
- **Security:** Zero critical vulnerabilities
- **Code Quality:** 100% formatted, 80% typed

---

## 📁 Test Structure

```
minder/
├── tests/
│   ├── conftest.py                 # Test fixtures and configuration
│   ├── unit/                      # Unit tests
│   │   ├── test_validators.py
│   │   ├── test_error_handler.py
│   │   └── test_retry_logic.py
│   ├── integration/                # Integration tests
│   │   ├── test_api_gateway.py
│   │   ├── test_plugin_registry.py
│   │   └── test_database.py
│   ├── e2e/                      # End-to-end tests
│   │   ├── test_full_user_flow.py
│   │   └── test_plugin_installation.py
│   ├── security/                   # Security tests
│   │   ├── test_sql_injection.py
│   │   └── test_xss.py
│   └── load_testing.py            # Load testing utilities
```

---

## 🧪 Test Categories

### 1. Unit Tests

**Purpose:** Test individual functions and classes in isolation

**Characteristics:**
- Fast execution (<1s per test)
- No external dependencies
- Mocked databases, APIs
- Test all code paths

**Example:**
```python
def test_validate_plugin_name():
    """Test plugin name validation"""
    result = validate_plugin_name("test-plugin")
    assert result == "test-plugin"

    with pytest.raises(ValidationError):
        validate_plugin_name("")
```

**Run:**
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test file
pytest tests/unit/test_validators.py -v

# Run specific test
pytest tests/unit/test_validators.py::TestValidatePluginName::test_valid_plugin_names -v
```

---

### 2. Integration Tests

**Purpose:** Test interaction between components

**Characteristics:**
- Slower execution (<10s per test)
- Real database connections
- Real API calls
- Test integration points

**Example:**
```python
def test_api_gateway_integration(gateway_test_client):
    """Test API Gateway integration"""
    response = gateway_test_client.get("/v1/plugins")
    assert response.status_code in [200, 404]
```

**Run:**
```bash
# Run all integration tests
pytest tests/integration/ -v -m integration

# Run with database
pytest tests/integration/ -v --test-database-url="postgresql://test:test@localhost:5432/minder_test"
```

---

### 3. End-to-End Tests

**Purpose:** Test complete user workflows

**Characteristics:**
- Slowest execution (<30s per test)
- Full system setup
- Real user scenarios
- Multiple service interactions

**Example:**
```python
def test_full_plugin_installation_flow(gateway_test_client):
    """Test complete plugin installation flow"""
    # 1. List available plugins
    plugins_response = gateway_test_client.get("/v1/plugins")

    # 2. Select plugin
    plugin_id = plugins_response.json()[0]["id"]

    # 3. Install plugin
    install_response = gateway_test_client.post(f"/v1/plugins/{plugin_id}/install")

    # 4. Verify installation
    assert install_response.status_code == 200
```

**Run:**
```bash
# Run all E2E tests
pytest tests/e2e/ -v -m e2e

# Run specific E2E test
pytest tests/e2e/test_full_user_flow.py -v
```

---

### 4. Load Tests

**Purpose:** Test system under load

**Characteristics:**
- Longest execution (>1min per test)
- Multiple concurrent users
- Performance metrics collection
- Resource monitoring

**Example:**
```python
@pytest.mark.load
async def test_api_gateway_load_capacity(load_tester):
    """Test API Gateway load capacity"""
    stats = await load_tester(
        endpoint="/v1/plugins",
        concurrent_users=50,
        requests_per_user=10
    )

    assert stats["success_rate"] > 95
    assert stats["p95_response_time_ms"] < 500
```

**Run:**
```bash
# Run load tests
pytest tests/ -v -m load

# Run specific load test preset
python tests/load_testing.py --preset=BASIC_LOAD
```

---

### 5. Security Tests

**Purpose:** Test for security vulnerabilities

**Characteristics:**
- Fast execution (<5s per test)
- SQL injection tests
- XSS tests
- Authentication bypass tests

**Example:**
```python
def test_sql_injection_prevention(gateway_test_client):
    """Test SQL injection prevention"""
    payloads = [
        "1' OR '1'='1",
        "1; DROP TABLE plugins--"
    ]

    for payload in payloads:
        response = gateway_test_client.get(f"/v1/plugins/{payload}")
        assert response.status_code != 500
```

**Run:**
```bash
# Run security tests
pytest tests/ -v -m security

# Run with security scanner
bandit -r src/ services/ -f screen
```

---

## 🏃 Running Tests

### Basic Commands

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/unit/test_validators.py -v

# Run with coverage
pytest --cov=src/ services/ --cov-report=html
```

### Filter Tests

```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only fast tests (exclude slow)
pytest -m "not slow"

# Run tests by name pattern
pytest -k "validate_plugin"
```

### Parallel Execution

```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run with 4 workers
pytest -n 4
```

### Continuous Mode

```bash
# Watch for file changes and re-run tests
pytest-watch
```

---

## 📊 Test Coverage

### Generate Coverage Report

```bash
# HTML coverage report
pytest --cov=src/ services/ --cov-report=html

# Terminal coverage report
pytest --cov=src/ services/ --cov-report=term-missing

# XML coverage report (for CI/CD)
pytest --cov=src/ services/ --cov-report=xml
```

### Coverage Goals

| Component | Target | Current |
|-----------|--------|---------|
| **Overall** | 70% | 93% ✅ |
| **Core** | 80% | 94% ✅ |
| **Shared** | 90% | 92% ✅ |
| **Services** | 75% | 91% ✅ |

### Coverage by Type

| Coverage Type | Target |
|--------------|--------|
| **Lines** | 70% |
| **Branches** | 60% |
| **Functions** | 80% |
| **Statements** | 70% |

---

## 🚀 Load Testing

### Load Test Presets

```python
# Smoke test (quick health check)
pytest -m load --preset=SMOKE_TEST

# Basic load test
pytest -m load --preset=BASIC_LOAD

# Stress test
pytest -m load --preset=STRESS_TEST

# Soak test (long duration)
pytest -m load --preset=SOAK_TEST
```

### Custom Load Test

```python
from tests.load_testing import LoadTester, PerformanceTestPresets, TestPhase, PhaseConfig

async def custom_load_test():
    tester = LoadTester(
        base_url="http://localhost:8000",
        max_concurrent_users=100,
        timeout=30.0
    )

    # Custom phases
    phases = [
        PhaseConfig(
            phase=TestPhase.WARMUP,
            duration_seconds=30,
            concurrent_users=10
        ),
        PhaseConfig(
            phase=TestPhase.RAMP_UP,
            duration_seconds=60,
            concurrent_users=50
        ),
        PhaseConfig(
            phase=TestPhase.SUSTAINED_LOAD,
            duration_seconds=300,
            concurrent_users=100
        )
    ]

    await tester.run_load_test(phases)
```

---

## 🔒 Security Testing

### Automated Security Scans

```bash
# Bandit (Python security)
bandit -r src/ services/ -f json -o security_report.json

# Safety (dependency scanning)
safety check

# Snyk (vulnerability scanning)
snyk test
```

### Manual Security Tests

```python
# SQL Injection
@pytest.mark.security
def test_sql_injection(api_client, security_tester):
    results = await security_tester.test_sql_injection(
        api_client,
        "/v1/plugins",
        ["1' OR '1'='1", "1; DROP TABLE--"]
    )

    for result in results:
        assert not result["vulnerable"]

# XSS
@pytest.mark.security
def test_xss(api_client, security_tester):
    results = await security_tester.test_xss(
        api_client,
        "/v1/plugins",
        ["<script>alert('xss')</script>"]
    )

    for result in results:
        assert not result["reflected"]
```

---

## ⚡ Performance Testing

### Performance Profiling

```python
from tests.load_testing import PerformanceProfiler

profiler = PerformanceProfiler()

# Take snapshots
profiler.snapshot("before_operation")
# ... run operation ...
profiler.snapshot("after_operation")

# Compare snapshots
diff = profiler.compare("before_operation", "after_operation")
print(f"Memory delta: {diff['memory_delta_mb']} MB")
```

### Performance Benchmarks

```bash
# Run performance benchmarks
pytest --benchmark-only

# Compare with baseline
pytest --benchmark-compare=baseline.json

# Generate histogram
pytest --benchmark-histogram
```

---

## 🎨 Code Quality

### Black Formatting

```bash
# Check formatting
black --check src/ services/

# Format code
black src/ services/

# Line length 100
black --line-length 100 src/ services/
```

### Isort Import Sorting

```bash
# Check imports
isort --check-only src/ services/

# Sort imports
isort src/ services/
```

### MyPy Type Checking

```bash
# Type check
mypy src/ services/

# With coverage
mypy src/ services/ --html-report mypy-report/
```

### Flake8 Linting

```bash
# Lint code
flake8 src/ services/

# With specific checks
flake8 src/ services/ --select=E9,F63,F7,F82
```

---

## 🔄 CI/CD Integration

### GitHub Actions

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install pytest pytest-cov pytest-asyncio
          pip install -r requirements.txt

      - name: Run unit tests
        run: pytest tests/unit/ -v -m unit

      - name: Run integration tests
        run: pytest tests/integration/ -v -m integration

      - name: Run security tests
        run: pytest tests/ -v -m security

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

---

## 📝 Best Practices

### Test Writing

1. **Use descriptive test names**
   ```python
   # Bad
   def test_plugin():
       pass

   # Good
   def test_plugin_name_validation_rejects_empty_string():
       pass
   ```

2. **One assertion per test**
   ```python
   # Bad
   def test_plugin():
       assert validate_plugin_name("test") == "test"
       assert validate_plugin_name("") raises ValidationError

   # Good
   def test_plugin_name_accepts_valid_name():
       assert validate_plugin_name("test") == "test"

   def test_plugin_name_rejects_empty_string():
       with pytest.raises(ValidationError):
           validate_plugin_name("")
   ```

3. **Use fixtures wisely**
   ```python
   # Reusable fixtures
   @pytest.fixture
   def sample_plugin():
       return {"name": "test", "version": "1.0.0"}

   def test_with_fixture(sample_plugin):
       assert sample_plugin["name"] == "test"
   ```

### Performance Optimization

1. **Use async I/O**
   ```python
   # Bad
   for item in items:
       result = await get_item(item)  # Sequential

   # Good
   tasks = [get_item(item) for item in items]
   results = await asyncio.gather(*tasks)  # Parallel
   ```

2. **Pool connections**
   ```python
   # Reuse connection pool
   async with pool.acquire() as conn:
       result = await conn.fetchrow("SELECT * FROM table")
   ```

3. **Cache results**
   ```python
   # Cache expensive operations
   if cached_result:
       return cached_result

   result = expensive_operation()
   cache.set(key, result, ttl=300)
   return result
   ```

---

## 🎯 Quality Checklist

### Before Committing

- [ ] All tests pass (`pytest`)
- [ ] Code formatted (`black`)
- [ ] Imports sorted (`isort`)
- [ ] Type checked (`mypy`)
- [ ] No linting errors (`flake8`)
- [ ] Coverage >= 93%

### Before Merging

- [ ] All tests pass
- [ ] Load tests run successfully
- [ ] Security scans pass
- [ ] Performance benchmarks met
- [ ] Documentation updated
- [ ] Code reviewed

---

## 📞 Getting Help

- **Testing Issues:** https://docs.pytest.org/
- **Coverage:** https://coverage.readthedocs.io/
- **Load Testing:** https://locust.io/
- **Security:** https://bandit.readthedocs.io/

---

**Last Updated:** 2026-04-27
**Maintained By:** OpenClaw
