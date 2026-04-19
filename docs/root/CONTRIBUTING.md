# Contributing to Minder

Thank you for your interest in contributing to Minder! This document provides guidelines and instructions for contributing to the project.

## 🤝 How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include:

- **Clear title and description**: Summarize the issue
- **Steps to reproduce**: Detailed steps to reproduce the behavior
- **Expected behavior**: What you expected to happen
- **Actual behavior**: What actually happened
- **Environment**: 
  - OS and version
  - Python version
  - Docker version (if applicable)
  - Relevant logs or error messages

### Suggesting Enhancements

Enhancement suggestions are welcome! Please provide:

- **Clear use case**: What problem would this solve?
- **Proposed solution**: How should it work?
- **Alternatives considered**: What other approaches did you consider?
- **Impact**: Who would benefit and how?

## 🛠️ Development Setup

### Prerequisites

- Docker and Docker Compose
- Python 3.13+
- Git
- Make (optional, for using Makefile commands)

### Setup Steps

1. **Fork and clone the repository**:
   ```bash
   git clone https://github.com/YOUR_USERNAME/minder.git
   cd minder
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # For development tools
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

5. **Start the development environment**:
   ```bash
   docker-compose up -d
   ```

6. **Run tests**:
   ```bash
   pytest tests/ -v
   ```

## 📝 Code Style

We follow PEP 8 guidelines with some modifications:

- **Line length**: Max 100 characters (soft limit)
- **Imports**: Group imports (stdlib, third-party, local)
- **Docstrings**: Google style docstrings
- **Type hints**: Required for all public functions

### Formatting

```bash
# Format code with Black
black .

# Sort imports with isort
isort .

# Lint with Flake8
flake8 .

# Type check with mypy (optional)
mypy .
```

## 🧪 Testing

### Test Structure

```
tests/
├── integration/     # Integration tests
├── unit/            # Unit tests
└── conftest.py      # pytest configuration
```

### Writing Tests

- **Unit tests**: Test individual functions/classes in isolation
- **Integration tests**: Test component interactions
- **Fixtures**: Use `conftest.py` for shared fixtures

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_auth.py -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test
pytest tests/test_auth.py::test_login -v
```

### Test Coverage

We aim for >80% code coverage. Check coverage reports in `htmlcov/index.html` after running tests with coverage.

## 📦 Plugin Development

### Plugin Structure

```
my_plugin/
├── plugin.yml           # Plugin metadata
├── __init__.py          # Plugin initialization
├── module.py            # Main plugin implementation
└── tests/               # Plugin-specific tests
    └── test_module.py
```

### Plugin Template

```python
from core.module_interface import BaseModule, ModuleMetadata

class MyPlugin(BaseModule):
    """Description of my plugin"""
    
    async def register(self) -> ModuleMetadata:
        return ModuleMetadata(
            name="my-plugin",
            version="1.0.0",
            description="My custom plugin",
            author="Your Name"
        )
    
    async def collect_data(self, since=None):
        """Collect data from external sources"""
        # Implementation here
        return {'records_collected': 0}
    
    async def analyze(self, data):
        """Analyze collected data"""
        # Implementation here
        return {}
```

For detailed plugin development guide, see [docs/development/module-development.md](docs/development/module-development.md).

## 🚀 Pull Request Process

### Before Submitting

1. **Update documentation**: Include relevant docstrings and README updates
2. **Add tests**: Ensure new code is tested
3. **Run tests**: All tests must pass
4. **Format code**: Run Black and isort
5. **Check linting**: No Flake8 errors

### Submitting a PR

1. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Commit your changes**:
   ```bash
   git commit -m "feat: add your feature description"
   ```

   **Commit message format**:
   - `feat:` New feature
   - `fix:` Bug fix
   - `docs:` Documentation changes
   - `style:` Code style changes (formatting)
   - `refactor:` Code refactoring
   - `test:` Adding or updating tests
   - `chore:` Maintenance tasks

3. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

4. **Create a Pull Request**:
   - Clear title describing the change
   - Detailed description of what you did and why
   - Reference related issues
   - Include screenshots if applicable

### PR Review Process

- **Automated checks**: CI/CD pipeline runs tests
- **Code review**: Maintainers review your code
- **Feedback**: Address review comments
- **Approval**: Once approved, your PR will be merged

## 🎯 Development Priorities

Current areas where we're looking for contributions:

- **High Priority**:
  - Additional plugin implementations
  - Test coverage improvements
  - Documentation enhancements

- **Medium Priority**:
  - Performance optimizations
  - UI/UX improvements
  - Integration examples

- **Low Priority**:
  - Code refactoring
  - Dependency updates
  - Feature requests

## 📜 License

By contributing to Minder, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## 🙋 Getting Help

- **GitHub Issues**: For bug reports and feature requests
- **Discussions**: For questions and ideas
- **Documentation**: Check [docs/](docs/) first

## 🌟 Recognition

Contributors will be recognized in:
- CONTRIBUTORS.md file
- Release notes
- Project documentation

Thank you for contributing to Minder! 🎉
