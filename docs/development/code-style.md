# Minder Platform - Code Style Guide

**Version:** 1.0.0
**Last Updated:** 2026-07-10
**Status:** Enforced (via CI `quality.yml`)

---

## Table of Contents

1. [Overview](#overview)
2. [Tooling & Configuration](#tooling--configuration)
3. [Python Style Standards](#python-style-standards)
4. [Type Hints](#type-hints)
5. [Documentation Standards](#documentation-standards)
6. [Naming Conventions](#naming-conventions)
7. [Error Handling Patterns](#error-handling-patterns)
8. [Code Organization](#code-organization)
9. [Testing Standards](#testing-standards)
10. [Git Commit Standards](#git-commit-standards)

---

## Overview

This guide defines the coding standards for the Minder platform. All contributors should
follow these standards to keep the codebase consistent and reviewable.

All services are **Python** (3.11 / 3.12) **FastAPI** applications. Formatting and import
ordering are enforced by the CI quality gate; the tooling configuration lives in the
**root `pyproject.toml`** (the single home for Python tool config).

**Philosophy:**
> "Code is read more often than it is written. Prioritize readability and consistency."

---

## Tooling & Configuration

The CI `quality.yml` workflow is the source of truth for what is enforced. It runs the
following against the codebase:

| Tool | Purpose | Config source |
|------|---------|---------------|
| **Black** | Code formatting | `[tool.black]` in root `pyproject.toml` |
| **isort** | Import ordering | `[tool.isort]` in root `pyproject.toml` |
| **mypy** | Static type checking | root `pyproject.toml` |
| **bandit** | Security linting (light scan) | CI |
| **safety** | Dependency vulnerability scan | CI |

**Key config values (root `pyproject.toml`):**

- **Black:** line length **88** (the Black default), `target-version = py311`.
- **isort:** `profile = "black"`, `known_first_party = ["config"]` (the service-local
  `config` module is treated as first-party so import ordering stays stable).
- **pytest:** `asyncio_mode = "auto"` (async tests do not need an explicit marker).

> Do not add per-service or ad-hoc tool config files. Shared dependency pins live in
> `src/requirements/`; Python tool config lives in the root `pyproject.toml`.

**Running the tools locally:**

```bash
# Format
black src/

# Check formatting without writing
black --check src/

# Sort imports
isort src/

# Check import order without writing
isort --check-only src/

# Type check
mypy src/
```

---

## Python Style Standards

### PEP 8 + Black

All code follows PEP 8 as enforced by Black. Notable points:

1. **Line length:** 88 characters (Black default — do not override).
2. **String quotes:** Black normalizes to double quotes.
3. **Import order:** managed by isort (`black` profile).
4. **Indentation:** 4 spaces, no tabs.

Because Black auto-formats, most style questions are settled by running `black src/`.

**Example:**
```python
# CORRECT
async def collect_data(self, since: Optional[datetime] = None) -> Dict[str, int]:
    """Collect data from external sources."""
    if since is None:
        since = datetime.now() - timedelta(hours=1)

    results = await self._fetch_data(since)
    return {"records_collected": len(results)}

# INCORRECT (unformatted)
async def collect_data(self,since:Optional[datetime]=None)->Dict[str,int]:
    results=await self._fetch_data(since)
    return {'records_collected':len(results)}
```

---

## Type Hints

Type hints are expected on public functions (parameters and return values). mypy runs in
CI, so annotate new and modified code.

```python
from typing import Any, Dict, List, Optional
from datetime import datetime


async def fetch_data(
    source: str,
    since: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Fetch data from a source."""
    ...
```

Guidelines:

1. Use specific container types (`List[str]`, `Dict[str, int]`) over bare `list`/`dict`.
2. Use `Optional[...]` for nullable values.
3. Use `TypedDict` for structured dict payloads where it aids clarity.

---

## Documentation Standards

### Docstrings

Public functions, classes, and methods should have docstrings. Google-style is preferred:

```python
async def ingest_document(self, path: str) -> Dict[str, Any]:
    """
    Ingest a document into the RAG pipeline.

    Args:
        path: Path to the source document (PDF/TXT/MD).

    Returns:
        A dict with keys `chunks` (int) and `knowledge_base` (str).

    Raises:
        ValueError: If the file type is unsupported.
    """
    ...
```

Every module should carry a short module docstring describing its purpose.

### Comments

- Explain **why**, not **what**.
- Don't comment out large blocks — delete them (git remembers).
- Don't leave bare `TODO`s without a tracking issue.

---

## Naming Conventions

Follow PEP 8:

1. **Modules/packages:** `lowercase_with_underscores`
2. **Classes:** `CapWords`
3. **Functions/variables:** `lowercase_with_underscores`
4. **Constants:** `UPPERCASE_WITH_UNDERSCORES`
5. **Private members:** `_leading_underscore`

---

## Error Handling Patterns

### Prefer specific exceptions

```python
# GOOD
try:
    data = await fetch_from_api()
except ConnectionError as e:
    logger.error(f"API connection failed: {e}")
    return []
except Exception:
    logger.exception("Unexpected error")
    raise

# BAD - bare except that swallows errors
try:
    data = await fetch_from_api()
except:
    pass
```

### Contextual error messages

```python
try:
    code = validate_code(raw)
except ValueError as e:
    raise ValueError(f"Invalid code '{raw}': {e}") from e
```

### Resource cleanup with context managers

```python
async with asyncpg.create_pool(dsn) as pool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1")
```

### Logging levels

```python
logger.debug("Detailed diagnostic information")
logger.info("General informational messages")
logger.warning("Unexpected but recoverable")
logger.error("Operation failed")
logger.critical("Critical system failure")
```

---

## Code Organization

Standard module layout:

```python
"""Module docstring."""

# 1. Standard library imports
import os
from datetime import datetime
from typing import Any, Dict, Optional

# 2. Third-party imports
import asyncpg
import httpx

# 3. Local imports
from config import settings

# 4. Module constants
MAX_RETRIES = 3

# 5. Logger
logger = logging.getLogger(__name__)

# 6. Class / function definitions
```

---

## Testing Standards

- Tests live under `tests/` (`unit`, `integration`, `e2e`, `performance`, `manual`,
  `fixtures`). See [testing.md](testing.md).
- Run with `pytest`. `asyncio_mode = "auto"` means async tests need no explicit marker.
- Test files: `test_{module}.py`; classes `Test{Name}`; methods `test_{behavior}`.

```python
import pytest


class TestValidator:
    def test_accepts_valid_name(self):
        assert validate_plugin_name("test") == "test"

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            validate_plugin_name("")
```

---

## Git Commit Standards

**Conventional Commits:**

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`.

**Example:**
```
feat(rag): add HyDE query expansion

Generates a hypothetical answer document and embeds it to improve
retrieval recall for sparse queries.

Closes #14
```

Co-author AI contributions where applicable:
```
Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Resources

- [PEP 8](https://peps.python.org/pep-0008/)
- [Black](https://black.readthedocs.io/)
- [isort](https://pycqa.github.io/isort/)
- [mypy](https://mypy-lang.org/)
- [Plugin Development Guide](plugin-development.md)
- [Testing Guide](testing.md)

---

**Config home:** root `pyproject.toml`. **Enforced by:** CI `quality.yml`.
