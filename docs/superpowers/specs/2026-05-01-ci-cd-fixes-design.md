# CI/CD Fixes Design

**Date:** 2026-05-01
**Priority:** MEDIUM - Deployment blocks
**Status:** Design Phase

## Problem Statement

Critical CI/CD workflow issues identified:

### 1. Wrong Directory Paths in Lint/Test

**Current (.github/workflows/ci.yml Lines 56-66):**
```yaml
# ❌ WRONG: These directories don't exist
- name: Run Flake8
  run: flake8 api/ core/ plugins/ ...

- name: Run Black
  run: black --check api/ core/ plugins/ ...

- name: Run MyPy
  run: mypy api/ --ignore-missing-imports ...
```

**Actual Project Structure:**
```
minder/
├── services/        # 9 microservices (NOT api/)
├── src/            # Source code (NOT core/)
│   ├── core/       # Core utilities
│   └── plugins/    # Plugin implementations
└── tests/          # Test suite
```

### 2. Wrong Coverage Paths

**Current (Lines 120-123):**
```python
pytest tests/ --ignore=tests/manual \
  --cov=api \          # ❌ WRONG
  --cov=core \         # ❌ WRONG
  --cov=plugins \      # ❌ WRONG
```

**Should be:**
```python
--cov=services \
--cov=src
```

### 3. Hidden Security Errors

**Current (Lines 22-29):**
```yaml
# ❌ HIDES ERRORS with "|| true"
- name: Run Bandit security linter
  run: |
    pip install bandit[toml]
    bandit -r api/ core/ -f json -o bandit-report.json || true

- name: Run Safety check
  run: |
    pip install safety
    safety check --json > safety-report.json || true
```

**Problem:** Security issues are silently ignored!

### 4. Missing Integration Tests

**Current (Lines 143-149):**
```yaml
# Integration Tests (Manual Only)
# Note: Integration tests require external API access and are run manually
# See tests/manual/README.md for details
#
# To run manually:
#   pytest tests/manual/ -v
#   python tests/manual/test_tefas_crawler.py
```

**Problem:** Integration tests never run in CI, potential bugs slip through.

## Proposed Solutions

### 1. Fix Directory Paths

**Update .github/workflows/ci.yml Lines 56-66:**
```yaml
# ✅ CORRECTED
- name: Run Flake8
  run: |
    pip install flake8
    flake8 services/ src/ --max-line-length=120 \
      --exclude=*.pyc,__pycache__,.git \
      --extend-ignore=E203,W503,E501

- name: Run Black
  run: |
    pip install black
    black --check services/ src/

- name: Run isort
  run: |
    pip install isort
    isort --check-only services/ src/

- name: Run MyPy
  run: |
    pip install mypy
    mypy services/ src/ --ignore-missing-imports || true
```

### 2. Fix Coverage Paths

**Update .github/workflows/ci.yml Lines 110-126:**
```python
# ✅ CORRECTED
- name: Run tests with coverage
  env:
    POSTGRES_HOST: localhost
    POSTGRES_PORT: 5432
    POSTGRES_USER: postgres
    POSTGRES_PASSWORD: test_password
    REDIS_HOST: localhost
    REDIS_PORT: 6379
  run: |
    pytest tests/ \
      --ignore=tests/manual \
      --cov=services \
      --cov=src \
      --cov-report=xml \
      --cov-report=html \
      --cov-report=term-missing \
      --cov-fail-under=80 \
      --verbose \
      --tb=short
```

### 3. Enable Security Failures

**Update .github/workflows/ci.yml Lines 22-37:**
```yaml
# ✅ SECURITY ISSUES NOW FAIL THE BUILD
- name: Run Bandit security linter
  run: |
    pip install bandit[toml]
    bandit -r services/ src/ -f json -o bandit-report.json
    # Check for high-severity issues
    if [ $(jq '.results[] | select(.severity == "HIGH") | length' bandit-report.json) -gt 0 ]; then
      echo "❌ High-severity security issues found"
      exit 1
    fi

- name: Run Safety check
  run: |
    pip install safety
    safety check --json > safety-report.json
    if [ $(jq '.vulnerabilities | length' safety-report.json) -gt 0 ]; then
      echo "❌ Security vulnerabilities found"
      exit 1
    fi

- name: Upload security reports
  uses: actions/upload-artifact@v4
  if: always()
  with:
    name: security-reports
    path: |
      bandit-report.json
      safety-report.json
```

### 4. Add Integration Tests

**Create new workflow: `.github/workflows/integration-tests.yml`**
```yaml
name: Integration Tests

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]
  schedule:
    # Run daily at 6 AM UTC
    - cron: '0 6 * * *'

env:
  PYTHON_VERSION: '3.12'

jobs:
  test-external-apis:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:latest
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-mock

      - name: Run integration tests
        env:
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: test_password
          REDIS_HOST: localhost
          REDIS_PORT: 6379
          # Skip actual external API calls
          SKIP_EXTERNAL_APIS: true
        run: |
          pytest tests/integration/ \
            --verbose \
            --tb=short \
            --timeout=300

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: integration-test-results
          path: |
            test-results/
            pytest-report.html

  test-manual-external:
    # Only run on schedule or manual trigger
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'
    timeout-minutes: 60

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-asyncio

      - name: Run manual external API tests
        env:
          # Allow actual external API calls
          EXTERNAL_API_TIMEOUT: 30
        run: |
          pytest tests/manual/ \
            --verbose \
            --tb=short \
            --timeout=600
        continue-on-error: true
```

### 5. Add Test Workflow Improvements

**Update .github/workflows/test.yml (if separate from ci.yml):**
```yaml
name: Test Suite

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main, develop ]

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ['3.11', '3.12']

    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432

      redis:
        image: redis:latest
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Cache pip packages
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/requirements*.txt') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run unit tests
        env:
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: test_password
          REDIS_HOST: localhost
          REDIS_PORT: 6379
        run: |
          pytest tests/unit/ \
            --cov=services \
            --cov=src \
            --cov-report=xml \
            --cov-report=html \
            --cov-report=term-missing \
            --cov-fail-under=85 \
            --verbose \
            --tb=short \
            --junitxml=test-results.xml

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          file: ./coverage.xml
          flags: unittests
          name: codecov-umbrella

      - name: Archive coverage reports
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-report-python-${{ matrix.python-version }}
          path: |
            coverage.xml
            htmlcov/
            test-results.xml
```

### 6. Fix Deployment Workflows

**Update deployment steps in ci.yml Lines 229-244:**
```yaml
- name: Deploy to production
  run: |
    echo "Deploying to production environment..."

    # Create backup before deployment
    echo "📦 Creating pre-deployment backup..."
    ssh ${{ secrets.PRODUCTION_HOST }} \
      "cd /root/minder && ./scripts/backup.sh pre-deploy"

    # Pull latest code
    echo "📥 Pulling latest code..."
    ssh ${{ secrets.PRODUCTION_HOST }} \
      "cd /root/minder && git pull origin main"

    # Run migrations (NEW!)
    echo "🔄 Running database migrations..."
    ssh ${{ secrets.PRODUCTION_HOST }} \
      "cd /root/minder && alembic upgrade head"

    # Restart services
    echo "🔄 Restarting services..."
    ssh ${{ secrets.PRODUCTION_HOST }} \
      "cd /root/minder && docker compose -f infrastructure/docker/docker-compose.yml up -d --build"

    # Wait for health check
    echo "⏳ Waiting for services to be healthy..."
    sleep 30

    # Run health check
    echo "🏥 Running health checks..."
    ssh ${{ secrets.PRODUCTION_HOST }} \
      "./scripts/health-check.sh"

- name: Verify deployment
  run: |
    curl -f https://minder.example.com/health || exit 1
    curl -f https://minder.example.com/api/v1/plugins || exit 1

- name: Rollback on failure
  if: failure()
  run: |
    echo "❌ Deployment failed, rolling back..."
    ssh ${{ secrets.PRODUCTION_HOST }} \
      "cd /root/minder && git reset --hard HEAD@{1} && alembic downgrade -1 && docker compose up -d"
```

### 7. Add Workflow Status Badges

**Add to README.md:**
```markdown
[![CI/CD Pipeline](https://github.com/wish-maker/minder/workflows/CI%2FCD%20Pipeline/badge.svg)](https://github.com/wish-maker/minder/actions/workflows/ci.yml)
[![Integration Tests](https://github.com/wish-maker/minder/workflows/Integration%20Tests/badge.svg)](https://github.com/wish-maker/minder/actions/workflows/integration-tests.yml)
[![Test Suite](https://github.com/wish-maker/minder/workflows/Test%20Suite/badge.svg)](https://github.com/wish-maker/minder/actions/workflows/test.yml)
```

## Implementation Order

### Phase 1: Fix Critical Paths (30 minutes)
1. ✅ Fix lint/test directory paths (services/, src/)
2. ✅ Fix coverage paths
3. ✅ Enable security failures

### Phase 2: Integration Tests (1 hour)
4. ✅ Create integration-tests.yml workflow
5. ✅ Add external API tests (with skip flag)
6. ✅ Add scheduled test runs

### Phase 3: Deployment Improvements (1 hour)
7. ✅ Add backup step to deployment
8. ✅ Add migration step to deployment
9. ✅ Add rollback automation

### Phase 4: Monitoring (30 minutes)
10. ✅ Add workflow status badges to README
11. ✅ Add test result uploads
12. ✅ Add coverage reporting

## Testing Strategy

1. **Test CI workflows** - Push to feature branch
2. **Verify security scans** - Intentionally add security issue
3. **Test integration tests** - Verify they run correctly
4. **Test deployment** - Dry-run deployment steps

## Success Criteria

✅ All linting uses correct directory paths
✅ Coverage reports include services/ and src/
✅ Security issues fail the build
✅ Integration tests run daily
✅ Deployments include backups and migrations
✅ Rollback is automated
✅ Workflow badges visible in README

## Estimated Timeline

- **Phase 1**: 30 minutes
- **Phase 2**: 1 hour
- **Phase 3**: 1 hour
- **Phase 4**: 30 minutes
- **Testing**: 1 hour

**Total**: 4 hours (0.5 days)

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| CI fails due to strict security | MEDIUM | Tune severity thresholds |
| Integration tests timeout | LOW | Increase timeout, add retries |
| Deployment rollback fails | HIGH | Test rollback in staging first |
| Coverage drops below threshold | MEDIUM | Investigate and fix tests |

---

## Approval Required

Before implementing:
1. ✅ Confirm security scan strictness (fail vs warn)
2. ✅ Confirm integration test frequency (daily vs weekly)
3. ✅ Confirm deployment automation level

**Next Steps:** Upon approval, proceed to implementation plan.
