# Minder Platform - Code Style Guide

**Version:** 1.0.0
**Last Updated:** 2026-04-23
**Status:** Enforced

---

## Table of Contents

1. [Overview](#overview)
2. [Python Style Standards](#python-style-standards)
3. [Type Hints Requirements](#type-hints-requirements)
4. [Documentation Standards](#documentation-standards)
5. [Naming Conventions](#naming-conventions)
6. [Error Handling Patterns](#error-handling-patterns)
7. [Code Organization](#code-organization)
8. [Testing Standards](#testing-standards)
9. [Git Commit Standards](#git-commit-standards)
10. [Pre-commit Hooks](#pre-commit-hooks)

---

## Overview

This guide defines the coding standards for the Minder platform. All contributors MUST follow these standards to ensure code quality, maintainability, and consistency.

**Enforcement Tools:**
- **Black** - Code formatting (auto-applied)
- **Flake8** - Linting (max line length: 120)
- **isort** - Import sorting
- **MyPy** - Type checking (planned)

**Philosophy:**
> "Code is read more often than it is written. Prioritize readability and consistency."

---

## Python Style Standards

### PEP 8 Compliance

All code MUST follow PEP 8 with these exceptions:

1. **Line Length:** Maximum 120 characters (not 79)
2. **Import Style:** Use `isort` for import organization
3. **String Quotes:** Prefer double quotes for consistency

### Code Formatting

**Auto-formatting with Black:**
```bash
black src/ services/ plugins/ tests/
```

**Formatting Rules:**
- 4 spaces for indentation (no tabs)
- 2 blank lines before top-level functions
- 1 blank line before method definitions
- No trailing whitespace
- One space after commas, no space before

**Example:**
```python
# ✅ CORRECT
async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
    """Collect data from external sources."""
    if since is None:
        since = datetime.now() - timedelta(hours=1)

    results = await self._fetch_data(since)
    return {"records_collected": len(results)}

# ❌ INCORRECT
async def collect_data(self,since:Optional[datetime]=None)->Dict[str,int]:
    """Collect data from external sources"""
    results=await self._fetch_data(since)
    return {'records_collected':len(results)}
```

---

## Type Hints Requirements

### Mandatory Type Hints

**All functions MUST have type hints for:**
- Parameters
- Return values
- Class attributes (complex types)

**Required in:**
- ✅ All new code
- ✅ Modified functions (add type hints when modifying)
- ✅ Public APIs (100% coverage)
- ✅ Plugin interfaces (BaseModule subclasses)

**Examples:**

```python
# ✅ CORRECT - Complete type hints
from typing import Dict, List, Optional, Any
from datetime import datetime

async def fetch_weather_data(
    location: str,
    since: Optional[datetime] = None
) -> Dict[str, Any]:
    """
    Fetch weather data for a location.

    Args:
        location: City name
        since: Start date for data collection

    Returns:
        Weather data dictionary
    """
    pass

# ❌ INCORRECT - Missing type hints
async def fetch_weather_data(location, since=None):
    """Fetch weather data."""
    pass
```

### Type Hint Best Practices

1. **Use specific types when possible:**
```python
# ✅ Good
def process_items(items: List[str]) -> Dict[str, int]:
    pass

# ❌ Too generic
def process_items(items) -> dict:
    pass
```

2. **Use Optional for nullable values:**
```python
# ✅ Good
def get_config(key: str) -> Optional[str]:
    return config.get(key)

# ❌ Ambiguous
def get_config(key: str) -> str:
    return config.get(key)  # Might return None
```

3. **Use TypedDict for structured data:**
```python
from typing import TypedDict

class WeatherData(TypedDict):
    location: str
    temperature: float
    humidity: int
    timestamp: datetime

def process_weather(data: WeatherData) -> float:
    return data["temperature"]
```

### Type Checking

**Planned:** MyPy integration for static type checking

```bash
# Future command
mypy src/ --strict
```

---

## Documentation Standards

### Docstring Requirements

**All public functions, classes, and methods MUST have docstrings.**

**Google Style Docstrings (Preferred):**

```python
def collect_fund_data(
    self,
    fund_code: str,
    start_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """
    Collect fund data from TEFAS API.

    Retrieves historical fund prices and metrics for the specified fund.
    Data includes daily prices, market cap, and number of shares.

    Args:
        fund_code: TEFAS fund code (e.g., "AAA")
        start_date: Start date for data collection. Defaults to 30 days ago.

    Returns:
        List of fund data dictionaries with keys:
        - date (datetime): Data date
        - price (float): Fund price
        - market_cap (float): Market capitalization
        - shares (int): Number of outstanding shares

    Raises:
        ValueError: If fund_code is invalid
        ConnectionError: If TEFAS API is unreachable

    Example:
        >>> plugin = TefasPlugin(config)
        >>> data = await plugin.collect_fund_data("AAA")
        >>> len(data)
        30
    """
    pass
```

### Docstring Sections

**Required Sections:**
1. **Brief Description:** One-line summary
2. **Detailed Description:** (optional) Extended explanation
3. **Args:** Parameters with types and descriptions
4. **Returns:** Return value description
5. **Raises:** Exceptions that may be raised
6. **Example:** (optional) Usage example

### Module-Level Documentation

**Every module MUST have a module docstring:**

```python
"""
Minder TEFAS Plugin

This plugin collects and analyzes Turkish mutual fund data from the
TEFAS (Turkey Fund Trading Platform) API.

Capabilities:
- Fund price data collection
- Risk metrics calculation
- Tax optimization analysis
- Portfolio allocation tracking

Author: Minder
Version: 1.0.0
"""
```

### Comment Guidelines

**When to Comment:**
- ✅ Explain "why" (not "what")
- ✅ Document non-obvious business logic
- ✅ Warn about potential issues
- ✅ Link to external resources

**When NOT to Comment:**
- ❌ Don't repeat obvious code
- ❌ Don't comment out large code blocks (delete instead)
- ❌ Don't leave TODO comments without creating issues

```python
# ✅ GOOD - Explains why
# Using exponential backoff to avoid overwhelming the API during outages
await asyncio.sleep(2 ** attempt)

# ❌ BAD - Obvious
# Increment the counter
counter += 1
```

---

## Naming Conventions

### General Rules

**Follow PEP 8 naming conventions:**

1. **Modules and Packages:** `lowercase_with_underscores`
   - ✅ `weather_plugin.py`
   - ✅ `services.rag_pipeline`
   - ❌ `WeatherPlugin.py`
   - ❌ `Services.RAG-Pipeline`

2. **Classes:** `CapitalizedWords` (CapWords convention)
   - ✅ `class WeatherModule(BaseModule):`
   - ✅ `class DatabaseConnection:`
   - ❌ `class weather_module:`
   - ❌ `class Weather_Module:`

3. **Functions and Variables:** `lowercase_with_underscores`
   - ✅ `def collect_data():`
   - ✅ `max_retries = 3`
   - ❌ `def CollectData():`
   - ❌ `def collectData():`

4. **Constants:** `UPPERCASE_WITH_UNDERSCORES`
   - ✅ `MAX_RETRIES = 3`
   - ✅ `DEFAULT_TIMEOUT = 30`
   - ❌ `maxRetries = 3`
   - ❌ `MAX_RETRIES = 3` # Inside a function (use lowercase)

5. **Private Members:** `_leading_underscore`
   - ✅ `def _internal_method():`
   - ✅ `self._private_var = 1`
   - ❌ `def internal_method():` # If intended to be private

### Plugin-Specific Conventions

**Plugin Files:**
- Main plugin file: `plugin.py` (not `weather_plugin.py`)
- Plugin class: `{Name}Module` (e.g., `WeatherModule`)
- Plugin directory: `lowercase` (e.g., `plugins/weather/`)

**Plugin Manifest:**
- Filename: `manifest.yml` (not `plugin.yml` or `config.yml`)
- Plugin name: `lowercase` (e.g., `weather`, not `Weather`)

---

## Error Handling Patterns

### Exception Hierarchy

```python
# Custom exceptions should inherit from appropriate base exceptions
class PluginError(Exception):
    """Base exception for plugin errors."""
    pass

class DataCollectionError(PluginError):
    """Raised when data collection fails."""
    pass

class ValidationError(PluginError):
    """Raised when input validation fails."""
    pass
```

### Error Handling Best Practices

**1. Specific Exception Handling:**

```python
# ✅ GOOD - Specific exceptions
try:
    data = await fetch_from_api()
except ConnectionError as e:
    logger.error(f"API connection failed: {e}")
    return []
except TimeoutError as e:
    logger.warning(f"API timeout, retrying: {e}")
    return await retry_fetch()
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise

# ❌ BAD - Bare except
try:
    data = await fetch_from_api()
except:
    pass  # Silent failure - dangerous!
```

**2. Contextual Error Messages:**

```python
# ✅ GOOD - Contextual message
try:
    fund_code = validate_fund_code(raw_code)
except ValueError as e:
    raise ValueError(
        f"Invalid fund code '{raw_code}': {e}. "
        f"Expected format: 3 uppercase letters (e.g., 'AAA')"
    ) from e

# ❌ BAD - Generic message
try:
    fund_code = validate_fund_code(raw_code)
except ValueError as e:
    raise ValueError("Invalid fund code") from e
```

**3. Resource Cleanup:**

```python
# ✅ GOOD - Context manager for cleanup
async with asyncpg.create_pool(dsn) as pool:
    async with pool.acquire() as conn:
        data = await conn.fetchrow("SELECT * FROM table")
    # Connection automatically released
# Pool automatically closed

# ❌ BAD - Manual cleanup (error-prone)
pool = await asyncpg.create_pool(dsn)
conn = await pool.acquire()
try:
    data = await conn.fetchrow("SELECT * FROM table")
finally:
    await conn.close()  # Easy to forget
    await pool.close()
```

### Logging Standards

**Use appropriate log levels:**

```python
logger.debug("Detailed diagnostic information")  # Development
logger.info("General informational messages")  # Production
logger.warning("Something unexpected but recoverable")  # Attention needed
logger.error("Error occurred, operation failed")  # Failure
logger.critical("Critical system failure")  # Urgent attention needed
```

**Structured Logging:**

```python
# ✅ GOOD - Structured log with context
logger.error(
    "Failed to collect weather data",
    extra={
        "location": location,
        "attempt": attempt,
        "error": str(e),
        "error_type": type(e).__name__
    }
)

# ❌ BAD - Unstructured log
logger.error(f"Failed for {location}, attempt {attempt}, error {e}")
```

---

## Code Organization

### File Structure

**Standard module structure:**

```python
"""
Module docstring
"""

# 1. Standard library imports
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

# 2. Third-party imports
import asyncpg
import aiohttp
from bs4 import BeautifulSoup

# 3. Local application imports
from src.core.interface import BaseModule, ModuleMetadata
from src.shared.database.postgres import get_connection
from src.plugins.weather.utils import parse_weather_data

# 4. Module constants
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# 5. Logger setup
logger = logging.getLogger(__name__)

# 6. Class definitions
class WeatherModule(BaseModule):
    """Weather data collection and analysis."""

    # 7. Public methods
    async def collect_data(self) -> Dict[str, Any]:
        """Collect weather data."""
        pass

    # 8. Private methods
    async def _fetch_data(self) -> Dict[str, Any]:
        """Fetch data from API."""
        pass

# 9. Standalone functions (if any)
def helper_function() -> str:
    """Helper function."""
    pass
```

### Class Organization

```python
class ExampleModule(BaseModule):
    """Organized class structure."""

    # 1. Class attributes
    _class_var: str = "value"

    # 2. __init__ method
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self._instance_var: int = 0

    # 3. Public lifecycle methods
    async def register(self) -> ModuleMetadata:
        """Register the module."""
        pass

    async def initialize(self) -> None:
        """Initialize the module."""
        pass

    async def shutdown(self) -> None:
        """Cleanup resources."""
        pass

    # 4. Public interface methods
    async def collect_data(self) -> Dict[str, Any]:
        """Collect data."""
        pass

    async def analyze(self) -> Dict[str, Any]:
        """Analyze data."""
        pass

    # 5. Private methods (alphabetical order)
    async def _cleanup(self) -> None:
        """Cleanup resources."""
        pass

    async def _validate_input(self, data: Any) -> bool:
        """Validate input data."""
        pass
```

---

## Testing Standards

### Test Coverage Requirements

**Current Target:** 30% minimum coverage
**Future Target:** 60% minimum coverage

**Critical Paths MUST Have Tests:**
- ✅ Plugin registration and initialization
- ✅ Data collection functions
- ✅ Error handling paths
- ✅ Database operations
- ✅ API integrations

### Test Structure

```python
# tests/plugins/test_weather.py
import pytest
from datetime import datetime
from src.plugins.weather.plugin import WeatherModule

class TestWeatherModule:
    """Weather plugin tests."""

    @pytest.fixture
    async def plugin(self):
        """Create plugin instance for testing."""
        config = {
            "database": {"host": "localhost"},
            "redis": {"host": "localhost"}
        }
        plugin = WeatherModule(config)
        await plugin.register()
        yield plugin
        await plugin.shutdown()

    @pytest.mark.asyncio
    async def test_collect_data(self, plugin):
        """Test data collection."""
        result = await plugin.collect_data()
        assert "records_collected" in result
        assert result["records_collected"] > 0

    @pytest.mark.asyncio
    async def test_collect_data_with_since(self, plugin):
        """Test data collection with date filter."""
        since = datetime.now() - timedelta(hours=1)
        result = await plugin.collect_data(since=since)
        assert result["records_collected"] >= 0
```

### Test Naming

**Test file names:** `test_{module_name}.py`
- ✅ `test_weather.py`
- ❌ `weather_tests.py`

**Test class names:** `Test{ClassName}`
- ✅ `class TestWeatherModule:`
- ❌ `class WeatherModuleTests:`

**Test method names:** `test_{what_is_being_tested}`
- ✅ `def test_collect_data_with_invalid_date():`
- ❌ `def test1():`

---

## Git Commit Standards

### Commit Message Format

**Conventional Commits (Required):**

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, no logic change)
- `refactor`: Code refactoring
- `test`: Test additions/changes
- `chore`: Maintenance tasks
- `perf`: Performance improvements

**Examples:**

```
feat(weather): Add humidity data collection

- Add humidity field to weather data schema
- Update Open-Meteo API parameters
- Add unit tests for humidity parsing

Closes #123
```

```
fix(tefas): Handle API timeout gracefully

Previously, TEFAS API timeouts would crash the plugin.
Now implements exponential backoff retry logic.

Fixes #456
```

### Commit Best Practices

1. **One logical change per commit**
2. **Write clear, descriptive subject lines** (max 50 chars)
3. **Use body to explain "why" not "what"**
4. **Reference issues in footer**
5. **Co-author-by for AI contributions:**
   ```
   Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
   ```

---

## Pre-commit Hooks

### Current Configuration

**File:** `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/psf/black
    rev: 24.3.0
    hooks:
      - id: black
        language_version: python3.11

  - repo: https://github.com/pycqa/flake8
    rev: 7.0.0
    hooks:
      - id: flake8
        args: ['--max-line-length=120']

  - repo: https://github.com/pycqa/isort
    rev: 5.13.2
    hooks:
      - id: isort
        args: ['--profile', 'black']
```

### Running Hooks

**Manual run:**
```bash
pre-commit run --all-files
```

**Skip hooks (not recommended):**
```bash
git commit --no-verify
```

### Planned Additions

**Future hooks:**
- ✅ `mypy` - Type checking
- ✅ `bandit` - Security linting
- ✅ `pytest` - Run tests before commit
- ✅ `pylint` - Code quality checks

---

## Code Review Checklist

**Before submitting code for review, verify:**

- [ ] All functions have type hints
- [ ] All public functions have docstrings
- [ ] Code follows PEP 8 (check with flake8)
- [ ] No trailing whitespace (check with black)
- [ ] Error handling implemented
- [ ] Logging added for important events
- [ ] Tests added for new functionality
- [ ] Commit message follows conventions
- [ ] Documentation updated (if needed)
- [ ] No hardcoded credentials or sensitive data

---

## Resources

**Official Standards:**
- [PEP 8](https://peps.python.org/pep-0008/)
- [PEP 257 (Docstrings)](https://peps.python.org/pep-0257/)
- [PEP 484 (Type Hints)](https://peps.python.org/pep-0484/)

**Tools:**
- [Black](https://black.readthedocs.io/)
- [Flake8](https://flake8.pycqa.org/)
- [isort](https://pycqa.github.io/isort/)
- [MyPy](http://mypy-lang.org/)

**Internal Documentation:**
- [Plugin Development Guide](PLUGIN_DEVELOPMENT.md)
- [Architecture Documentation](architecture.md)
- [API Documentation](docs/api/README.md)

---

**Questions?** Check existing code in `src/plugins/` for examples of these standards in practice.
