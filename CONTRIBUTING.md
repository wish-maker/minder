# Contributing to Minder

Thank you for your interest in contributing to Minder! This document provides guidelines for contributing to the project.

## 🤝 How to Contribute

### Reporting Issues

Before creating an issue, please:

1. Search for existing issues
2. Check if the issue is already resolved
3. Provide clear description including:
   - Steps to reproduce
   - Expected behavior
   - Actual behavior
   - Environment details (OS, Python version, etc.)

### Submitting Pull Requests

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Follow the code style guide
5. Add tests for new features
6. Update documentation
7. Submit a pull request

## 📋 Code Style Guidelines

### Python

- Follow PEP 8
- Use type hints
- Add docstrings to all functions and classes
- Write unit tests for new code
- Follow naming conventions:
  - Classes: PascalCase
  - Functions: snake_case
  - Constants: UPPER_SNAKE_CASE
  - Private functions: _leading_underscore

### Type Hints

```python
from typing import List, Dict, Optional, Any

def example_function(
    param1: str,
    param2: Optional[int] = None
) -> Dict[str, Any]:
    """
    Example function with type hints.

    Args:
        param1: Description
        param2: Description

    Returns:
        Dictionary with results
    """
    return {"param1": param1, "param2": param2}
```

### Docstrings

```python
def example_function(param1: str, param2: int) -> str:
    """
    Brief description.

    Detailed description.

    Args:
        param1: Description of param1
        param2: Description of param2

    Returns:
        Description of return value

    Raises:
        ValueError: Description of error
    """
    return f"{param1}-{param2}"
```

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests
pytest tests/unit/

# Run integration tests
pytest tests/integration/

# Run E2E tests
pytest tests/e2e/

# Run with coverage
pytest --cov=src --cov-report=html
```

### Writing Tests

1. Write unit tests for new functions
2. Write integration tests for new features
3. Write E2E tests for complete workflows
4. Use fixtures for common test data
5. Keep tests simple and focused

## 📖 Documentation

### Updating Documentation

1. Update API documentation for new endpoints
2. Update architecture docs for new components
3. Update user guides for new features
4. Update troubleshooting docs for known issues

### Documentation Style

- Use clear, concise language
- Include code examples
- Use diagrams where helpful
- Update dates on changes

## 🔍 Code Review

### Before Submitting

1. Run linters: `flake8 src/services/ src/shared/ scripts/ tests/ --max-line-length=120`
2. Run type checking **per service** (each service dir is its own import root):
   `for d in src/services/*/; do (cd "$d" && mypy . --config-file "$PWD/../../../pyproject.toml"); done`
   (checking all of `src/` at once fails with "Duplicate module" — see `docs/development/`)
3. Run tests: `pytest`
4. Check code formatting: `black --check src/services/ src/shared/ scripts/ tests/` and `isort --check-only ...`
5. Update documentation
6. Write tests

### During Review

1. Address all review comments
2. Update tests as needed
3. Update documentation as needed
4. Keep PRs focused on single change
5. Maintain clear commit history

## 🚀 Getting Started

### Development Setup

```bash
# Clone repository
git clone git@github.com:wish-maker/minder.git
cd minder

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install development + type-check dependencies (there are no root requirements files;
# the pinned sets live under src/requirements/)
pip install -r src/requirements/requirements-dev.txt
pip install -r src/requirements/requirements-typecheck.txt

# Run tests
pytest
```

### Branch Naming

- `feature/` - New features
- `bugfix/` - Bug fixes
- `refactor/` - Refactoring
- `docs/` - Documentation changes

### Commit Messages

```
type(scope): brief description

Detailed description

- Bullet point 1
- Bullet point 2
```

Types:
- `feat` - New feature
- `fix` - Bug fix
- `docs` - Documentation change
- `style` - Code style change
- `refactor` - Refactoring
- `test` - Test change
- `chore` - Maintenance

Example:
```
feat(api): add plugin filtering endpoint

Add endpoint to filter plugins by name, category, and status.

- Add filtering parameters
- Add pagination support
- Update documentation
```

## 📋 Project Structure

```
minder/
├── src/                  # Application source
│   ├── services/         # Microservices (8 FastAPI apps)
│   ├── shared/           # Shared libraries (config, log, metrics, auth, db, utils)
│   ├── plugins/          # First-party module plugins (crypto, network, news, tefas, weather, telegraf)
│   ├── bootstrap/        # Bootstrap config data (config/default_plugins.yml)
│   └── requirements/     # Shared Python dependency sets
├── docker/               # Docker configuration (compose, services, templates)
├── tests/                # Test suite
├── docs/                 # Documentation
└── scripts/              # Setup & utility scripts (setup/, lib/, gate/)
```

## 🎯 Development Priorities

1. Code quality
2. Test coverage
3. Documentation
4. Performance
5. Security

## 📞 Contact

- Issues: https://github.com/wish-maker/minder/issues
- Discussions: https://github.com/wish-maker/minder/discussions

---

Happy contributing! 🎉
